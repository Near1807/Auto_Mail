"""Tâche d'envoi d'une campagne, dans un thread, avec pause / reprise / annulation.

La tâche publie des évènements (dict JSON) que l'API relaie au front en SSE :
``start``, ``sent``, ``error``, ``warning``, ``paused``, ``resumed``, ``label``, ``done``.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import tracking as tracking_mod
from .addresses import Recipient
from .gmail import AuthError, ImapSession, SmtpSession, default_imap_factory, default_smtp_factory, friendly_error
from .message import Draft, build_message, recipient_variables, render

GMAIL_DAILY_LIMIT = 500


@dataclass
class SendConfig:
    sender_email: str
    sender_name: str
    password: str
    draft: Draft
    recipients: list[Recipient]
    csv_path: Path
    label: str = ""
    delay_seconds: float = 3.0
    campaign_id: str = ""


@dataclass
class Job:
    config: SendConfig
    smtp_factory: Callable = default_smtp_factory
    imap_factory: Callable = default_imap_factory
    sleep: Callable[[float], None] = time.sleep
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = "pending"  # pending | running | paused | cancelled | done | failed
    sent: int = 0
    errors: int = 0
    skipped: int = 0
    current: str = ""
    events: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self._cond = threading.Condition()
        self._resume = threading.Event()
        self._resume.set()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._unsaved = False

    # ------------------------------------------------------------------ contrôle
    @property
    def total(self) -> int:
        return len(self.config.recipients)

    @property
    def finished(self) -> bool:
        return self.state in ("cancelled", "done", "failed")

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name=f"send-{self.id}", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def pause(self) -> None:
        if self.state == "running":
            self._resume.clear()
            self.state = "paused"
            self._emit("paused")

    def resume(self) -> None:
        if self.state == "paused":
            self.state = "running"
            self._resume.set()
            self._emit("resumed")

    def cancel(self) -> None:
        if not self.finished:
            self._cancel.set()
            self._resume.set()

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.config.campaign_id,
            "state": self.state,
            "total": self.total,
            "sent": self.sent,
            "errors": self.errors,
            "skipped": self.skipped,
            "current": self.current,
            "label": self.config.label,
        }

    def events_after(self, seq: int, timeout: float = 15.0) -> list[dict]:
        """Évènements de numéro > ``seq`` ; attend jusqu'à ``timeout`` s'il n'y en a pas."""
        with self._cond:
            if len(self.events) <= seq and not self.finished:
                self._cond.wait(timeout)
            return self.events[seq:]

    # ---------------------------------------------------------------- exécution
    def _emit(self, kind: str, **data) -> None:
        with self._cond:
            event = {"seq": len(self.events) + 1, "type": kind, "time": datetime.now().strftime("%H:%M:%S"),
                     **data, "progress": self.snapshot()}
            self.events.append(event)
            self._cond.notify_all()

    def _wait_if_paused(self) -> bool:
        """Bloque tant que la tâche est en pause ; ``False`` si elle est annulée."""
        while not self._resume.wait(0.2):
            if self._cancel.is_set():
                return False
        return not self._cancel.is_set()

    def _interruptible_sleep(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0 and not self._cancel.is_set():
            chunk = min(0.2, remaining)
            self.sleep(chunk)
            remaining -= chunk
            # Une pause pendant le délai : le décompte reprend à la reprise.
            if not self._resume.is_set() and not self._wait_if_paused():
                return

    def _save(self, tracking) -> None:
        try:
            tracking_mod.save(tracking, self.config.csv_path, sleep=self.sleep)
            if self._unsaved:
                self._emit("warning", code="csv_unlocked", message="Le fichier de suivi est de nouveau accessible : tout est enregistré.")
            self._unsaved = False
        except tracking_mod.CsvLockedError as error:
            if not self._unsaved:
                self._emit("warning", code="csv_locked", message=f"{error} L'envoi continue ; ferme le fichier pour que le suivi soit enregistré.")
            self._unsaved = True

    def run(self) -> None:
        cfg = self.config
        if self.state == "pending":
            self.state = "running"
        self._emit("start", sender=cfg.sender_email)
        tracking = tracking_mod.load(cfg.csv_path)
        sent_ids: list[str] = []
        smtp = SmtpSession(cfg.sender_email, cfg.password, factory=self.smtp_factory, sleep=self.sleep)
        try:
            smtp.connect()
        except AuthError as error:
            self.state = "failed"
            self._emit("done", ok=False, message=str(error))
            return
        except Exception as error:  # réseau
            self.state = "failed"
            self._emit("done", ok=False, message=friendly_error(error))
            return

        try:
            for index, recipient in enumerate(cfg.recipients):
                if not self._wait_if_paused():
                    break
                self.current = recipient.email
                # Filet de sécurité : le CSV fait foi, même si la liste a changé entre-temps.
                if tracking.is_sent(recipient.email):
                    self.skipped += 1
                    self._emit("skipped", email=recipient.email, message="Déjà envoyé")
                    continue
                variables = recipient_variables(recipient.email, recipient.fields)
                subject = render(cfg.draft.subject, variables)
                try:
                    msg = build_message(cfg.draft, cfg.sender_email, cfg.sender_name, recipient.email, variables)
                    smtp.send(msg)
                except AuthError as error:
                    tracking.mark_error(recipient.email, subject, str(error))
                    self.errors += 1
                    self._save(tracking)
                    self._emit("error", email=recipient.email, message=str(error))
                    self.state = "failed"
                    break
                except Exception as error:
                    message = friendly_error(error)
                    tracking.mark_error(recipient.email, subject, message)
                    self.errors += 1
                    self._save(tracking)
                    self._emit("error", email=recipient.email, message=message)
                else:
                    sent_ids.append(msg["Message-ID"])
                    tracking.mark_sent(recipient.email, subject)
                    self.sent += 1
                    self._save(tracking)
                    self._emit("sent", email=recipient.email)
                if index < len(cfg.recipients) - 1 and cfg.delay_seconds > 0:
                    self._interruptible_sleep(cfg.delay_seconds)
        finally:
            smtp.close()
            self.current = ""

        if self._unsaved:
            self._save(tracking)
            if self._unsaved:
                backup = cfg.csv_path.with_name(f"suivi-recupere-{datetime.now():%Y%m%d-%H%M%S}.csv")
                try:
                    tracking_mod.save(tracking, backup, sleep=self.sleep)
                    self._emit("warning", code="csv_backup", message=f"Le suivi n'a pas pu être écrit ; une copie a été enregistrée dans « {backup.name} ».")
                except tracking_mod.CsvLockedError:
                    pass

        if cfg.label and sent_ids:
            try:
                with ImapSession(cfg.sender_email, cfg.password, factory=self.imap_factory) as imap:
                    count, missing = imap.apply_label(sent_ids, cfg.label, sleep=self.sleep)
                message = f"Libellé « {cfg.label} » appliqué à {count} mail(s)."
                if missing:
                    message += f" {missing} mail(s) introuvable(s) dans « Envoyés » : libelle-les à la main."
                self._emit("label", ok=not missing, count=count, missing=missing, message=message)
            except Exception as error:
                self._emit("label", ok=False, count=0, message=f"Libellé non appliqué : {friendly_error(error)}")

        if self._cancel.is_set():
            self.state = "cancelled"
            self._emit("done", ok=True, message="Envoi annulé.")
        elif self.state == "failed":
            self._emit("done", ok=False, message="Envoi interrompu : Gmail refuse l'identification.")
        else:
            self.state = "done"
            self._emit("done", ok=True, message="Envoi terminé.")


def send_test(config: SendConfig, smtp_factory: Callable = default_smtp_factory) -> str:
    """Envoie le message à l'expéditeur lui-même (variables du 1er destinataire). Non suivi."""
    first = config.recipients[0] if config.recipients else Recipient(email=config.sender_email)
    variables = recipient_variables(first.email, first.fields)
    draft = Draft(subject="[TEST] " + config.draft.subject, mode=config.draft.mode,
                  text=config.draft.text, html=config.draft.html, attachments=config.draft.attachments)
    msg = build_message(draft, config.sender_email, config.sender_name, config.sender_email, variables)
    with SmtpSession(config.sender_email, config.password, factory=smtp_factory) as smtp:
        smtp.send(msg)
    return msg["Message-ID"]


def estimate_seconds(count: int, delay: float, per_mail: float = 1.5) -> float:
    return max(0, count) * per_mail + max(0, count - 1) * max(0.0, delay)
