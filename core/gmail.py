"""Accès Gmail : SMTP (une seule connexion, reconnexion auto) et IMAP (libellés, réponses).

Les fabriques ``smtp_factory`` / ``imap_factory`` sont injectables pour les tests :
aucun test n'ouvre de vraie connexion.
"""

from __future__ import annotations

import base64
import imaplib
import re
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Callable, Iterable

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
IMAP_HOST = "imap.gmail.com"


class AuthError(Exception):
    """Identifiants refusés par Gmail."""


def default_smtp_factory():
    return smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)


def default_imap_factory():
    return imaplib.IMAP4_SSL(IMAP_HOST)


def friendly_error(error: BaseException) -> str:
    if isinstance(error, smtplib.SMTPAuthenticationError) or isinstance(error, AuthError):
        return "Gmail refuse l'identification : vérifie l'adresse et le mot de passe d'application."
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        refused = next(iter(error.recipients.values()), (0, b""))
        detail = refused[1].decode(errors="replace") if isinstance(refused[1], bytes) else refused[1]
        return f"Adresse refusée par le serveur ({refused[0]}) : {detail}".strip()
    if isinstance(error, smtplib.SMTPResponseException):
        detail = error.smtp_error.decode(errors="replace") if isinstance(error.smtp_error, bytes) else str(error.smtp_error)
        return f"Erreur SMTP {error.smtp_code} : {detail}"
    if isinstance(error, (OSError, smtplib.SMTPServerDisconnected)):
        return f"Problème réseau : {error}"
    return str(error) or error.__class__.__name__


class SmtpSession:
    """Une connexion SMTP gardée ouverte pendant toute la campagne."""

    def __init__(self, email: str, password: str, factory: Callable = default_smtp_factory,
                 reconnect_attempts: int = 2, sleep=time.sleep):
        self.email = email
        self.password = password
        self.factory = factory
        self.reconnect_attempts = reconnect_attempts
        self.sleep = sleep
        self.conn = None

    def connect(self) -> None:
        self.close()
        conn = self.factory()
        try:
            conn.ehlo()
            conn.starttls(context=ssl.create_default_context())
            conn.ehlo()
            conn.login(self.email, self.password)
        except smtplib.SMTPAuthenticationError as error:
            _quietly(conn.quit)
            raise AuthError(friendly_error(error)) from error
        self.conn = conn

    def send(self, msg: EmailMessage) -> None:
        if self.conn is None:
            self.connect()
        for attempt in range(self.reconnect_attempts + 1):
            try:
                self.conn.send_message(msg)
                return
            except (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError) as error:
                # La connexion est tombée : on se reconnecte et on renvoie ce mail.
                if attempt >= self.reconnect_attempts:
                    raise
                self.sleep(1.5 * (attempt + 1))
                self.connect()

    def close(self) -> None:
        if self.conn is not None:
            _quietly(self.conn.quit)
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()


def _quietly(fn) -> None:
    try:
        fn()
    except Exception:
        pass


# --------------------------------------------------------------------------- IMAP


def imap_utf7_encode(text: str) -> str:
    """Encodage « modified UTF-7 » des noms de dossiers IMAP (RFC 3501 §5.1.3)."""
    out, buffer = [], []

    def flush():
        if buffer:
            encoded = base64.b64encode("".join(buffer).encode("utf-16-be")).decode().rstrip("=")
            out.append("&" + encoded.replace("/", ",") + "-")
            buffer.clear()

    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buffer.append(ch)
    flush()
    return "".join(out)


def imap_utf7_decode(text: str) -> str:
    def repl(match: re.Match) -> str:
        chunk = match.group(1)
        if not chunk:
            return "&"
        data = chunk.replace(",", "/")
        data += "=" * (-len(data) % 4)
        return base64.b64decode(data).decode("utf-16-be")

    return re.sub(r"&([A-Za-z0-9+,]*)-", repl, text)


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?P<sep>"[^"]*"|NIL) (?P<name>.+)$')


def parse_list_line(line: bytes) -> tuple[list[str], str] | None:
    match = _LIST_RE.match(line.strip())
    if not match:
        return None
    flags = match.group("flags").decode(errors="ignore").split()
    name = match.group("name").decode(errors="ignore").strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return flags, imap_utf7_decode(name)


class ImapSession:
    def __init__(self, email: str, password: str, factory: Callable = default_imap_factory):
        self.email = email
        self.password = password
        self.factory = factory
        self.conn = None

    def __enter__(self):
        conn = self.factory()
        try:
            conn.login(self.email, self.password)
        except imaplib.IMAP4.error as error:
            _quietly(conn.logout)
            raise AuthError(friendly_error(AuthError())) from error
        self.conn = conn
        return self

    def __exit__(self, *exc):
        if self.conn is not None:
            _quietly(self.conn.logout)
            self.conn = None

    def folders(self) -> list[tuple[list[str], str]]:
        typ, data = self.conn.list()
        if typ != "OK":
            return []
        return [parsed for line in data if isinstance(line, bytes) and (parsed := parse_list_line(line))]

    def special_folder(self, flag: str, fallback: str) -> str:
        for flags, name in self.folders():
            if flag in flags:
                return name
        return fallback

    def select(self, folder: str) -> None:
        typ, _ = self.conn.select(quote(imap_utf7_encode(folder)), readonly=False)
        if typ != "OK":
            raise RuntimeError(f"Dossier IMAP introuvable : {folder}")

    def ensure_label(self, label: str) -> None:
        """Crée le libellé (et ses parents ``a/b/c``) s'il n'existe pas."""
        existing = {name for _, name in self.folders()}
        parts = [p for p in label.split("/") if p.strip()]
        for i in range(1, len(parts) + 1):
            name = "/".join(parts[:i])
            if name not in existing:
                self.conn.create(quote(imap_utf7_encode(name)))
                existing.add(name)

    def apply_label(self, message_ids: Iterable[str], label: str,
                    attempts: int = 4, sleep=time.sleep) -> tuple[int, int]:
        """Applique le libellé aux mails envoyés (retrouvés par Message-ID).

        Gmail met parfois quelques secondes à indexer un mail envoyé : on réessaie.
        Retourne (mails libellés, mails introuvables dans « Envoyés »).
        """
        pending = list(message_ids)
        if not pending:
            return 0, 0
        self.ensure_label(label)
        self.select(self.special_folder("\\Sent", "[Gmail]/Sent Mail"))
        label_arg = "(" + quote(imap_utf7_encode(label)) + ")"
        done = 0
        for attempt in range(attempts):
            remaining = []
            for mid in pending:
                typ, data = self.conn.search(None, "HEADER", "Message-ID", quote(mid))
                nums = data[0].split() if typ == "OK" and data and data[0] else []
                if not nums:
                    remaining.append(mid)
                    continue
                for num in nums:
                    self.conn.store(num, "+X-GM-LABELS", label_arg)
                done += 1
            pending = remaining
            if not pending:
                break
            if attempt < attempts - 1:
                sleep(2.0)
                self.conn.noop()
        return done, len(pending)

    def find_replies(self, label: str) -> dict[str, datetime]:
        """Adresses qui ont répondu dans les fils du libellé → date de la première réponse."""
        self.select(self.special_folder("\\All", "[Gmail]/All Mail"))
        raw = "label:" + re.sub(r"[\s/]+", "-", label)
        typ, data = self.conn.search(None, "X-GM-RAW", quote(raw))
        nums = data[0].split() if typ == "OK" and data and data[0] else []
        if not nums:
            return {}
        own = self.email.lower()
        threads: dict[bytes, set[str]] = {}
        for num in nums:
            typ, fetched = self.conn.fetch(num, "(X-GM-THRID BODY.PEEK[HEADER.FIELDS (FROM TO CC)])")
            thrid, headers = _thread_and_headers(fetched)
            if thrid is None or headers is None:
                continue
            sender = _addresses(headers.get_all("From", []))
            if own in sender:
                recipients = _addresses(headers.get_all("To", []) + headers.get_all("Cc", []))
                threads.setdefault(thrid, set()).update(recipients - {own})

        replies: dict[str, datetime] = {}
        for thrid, recipients in threads.items():
            if not recipients:
                continue
            typ, data = self.conn.search(None, "X-GM-THRID", thrid.decode())
            for num in data[0].split() if typ == "OK" and data and data[0] else []:
                typ, fetched = self.conn.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM DATE)])")
                _, headers = _thread_and_headers(fetched)
                if headers is None:
                    continue
                for author in _addresses(headers.get_all("From", [])):
                    if author == own:
                        continue
                    when = _parse_date(headers.get("Date"))
                    # Une réponse d'une autre adresse du même fil compte pour tous ses destinataires.
                    targets = {author} if author in recipients else recipients
                    for target in targets:
                        if target not in replies or (when and when < replies[target]):
                            replies[target] = when or datetime.now()
        return replies


_THRID_RE = re.compile(rb"X-GM-THRID (\d+)")


def _thread_and_headers(fetched):
    for part in fetched or []:
        if isinstance(part, tuple) and len(part) >= 2:
            match = _THRID_RE.search(part[0])
            headers = BytesHeaderParser().parsebytes(part[1])
            return (match.group(1) if match else None), headers
    return None, None


def _addresses(values) -> set[str]:
    return {addr.strip().lower() for _, addr in getaddresses([str(v) for v in values]) if addr}


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def check_connection(email: str, password: str, smtp_factory=default_smtp_factory,
                    imap_factory=default_imap_factory) -> None:
    """Lève ``AuthError`` ou une autre exception si SMTP ou IMAP échoue."""
    with SmtpSession(email, password, factory=smtp_factory):
        pass
    with ImapSession(email, password, factory=imap_factory):
        pass
