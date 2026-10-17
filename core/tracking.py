"""CSV de suivi d'une campagne.

Format : séparateur ``;``, UTF-8 avec BOM (Excel l'ouvre proprement), colonnes
``email;status;reponse;date;objet;erreur``. Les anciens fichiers ``email;status;reponse``
(sans BOM) se lisent tels quels, et toute colonne ajoutée à la main est conservée.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .addresses import Recipient, normalize_email

BASE_COLUMNS = ["email", "status", "reponse", "date", "objet", "erreur"]
STATUS_SENT = "Envoyé"
STATUS_ERROR = "Erreur"
MAX_ERROR_LENGTH = 200  # comme app.py : la colonne reste lisible dans Excel


class CsvLockedError(Exception):
    """Le fichier est verrouillé (souvent : ouvert dans Excel)."""

    def __init__(self, path: Path):
        super().__init__(
            f"Impossible d'écrire « {path.name} » : le fichier est probablement ouvert dans Excel."
        )
        self.path = path


@dataclass
class TrackingRow:
    email: str
    values: dict[str, str] = field(default_factory=dict)  # toutes les colonnes sauf email

    @property
    def status(self) -> str:
        return self.values.get("status", "")

    def get(self, column: str) -> str:
        return self.email if column == "email" else self.values.get(column, "")


class Tracking:
    """Contenu d'un CSV de suivi, indexé par adresse en minuscules (ordre conservé)."""

    def __init__(self, rows: Iterable[TrackingRow] = (), extra_columns: Iterable[str] = ()):
        self.rows: dict[str, TrackingRow] = {}
        self.extra_columns: list[str] = [c for c in extra_columns if c not in BASE_COLUMNS]
        for row in rows:
            self._merge(row)

    def _merge(self, row: TrackingRow) -> None:
        key = normalize_email(row.email)
        existing = self.rows.get(key)
        if existing is None:
            self.rows[key] = TrackingRow(email=key, values=dict(row.values))
            return
        # Doublon dans le fichier : « Envoyé » l'emporte toujours, sinon la dernière ligne.
        if existing.status == STATUS_SENT and row.status != STATUS_SENT:
            for k, v in row.values.items():
                if v and not existing.values.get(k):
                    existing.values[k] = v
            return
        merged = dict(existing.values)
        merged.update({k: v for k, v in row.values.items() if v})
        merged["status"] = row.status
        existing.values = merged

    @property
    def columns(self) -> list[str]:
        return BASE_COLUMNS + self.extra_columns

    def status_of(self, email: str) -> str:
        row = self.rows.get(normalize_email(email))
        return row.status if row else ""

    def is_sent(self, email: str) -> bool:
        return self.status_of(email) == STATUS_SENT

    def mark_sent(self, email: str, subject: str, when: datetime | None = None) -> None:
        self._set(email, STATUS_SENT, subject, "", when)

    def mark_error(self, email: str, subject: str, error: str, when: datetime | None = None) -> None:
        self._set(email, STATUS_ERROR, subject, error, when)

    def _set(self, email: str, status: str, subject: str, error: str, when: datetime | None) -> None:
        key = normalize_email(email)
        row = self.rows.setdefault(key, TrackingRow(email=key))
        row.values.update(
            {
                "status": status,
                "date": (when or datetime.now()).strftime("%Y-%m-%d %H:%M"),
                "objet": subject,
                "erreur": error[:MAX_ERROR_LENGTH],
            }
        )
        row.values.setdefault("reponse", "")

    def set_value(self, email: str, column: str, value: str) -> None:
        key = normalize_email(email)
        if key not in self.rows:
            raise KeyError(email)
        if column == "email":
            raise ValueError("La colonne email n'est pas modifiable.")
        if column not in self.columns:
            self.extra_columns.append(column)
        self.rows[key].values[column] = value

    def counts(self) -> dict[str, int]:
        sent = sum(1 for r in self.rows.values() if r.status == STATUS_SENT)
        errors = sum(1 for r in self.rows.values() if r.status == STATUS_ERROR)
        replies = sum(1 for r in self.rows.values() if r.values.get("reponse", "").strip())
        return {"total": len(self.rows), "sent": sent, "errors": errors, "replies": replies}

    def to_csv_text(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(self.columns)
        for row in self.rows.values():
            writer.writerow([row.get(c) for c in self.columns])
        return buffer.getvalue()


def decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_csv_text(text: str) -> Tracking:
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return Tracking()
    delimiter = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip() for h in next(reader)]
    lowered = [h.lower() for h in header]
    if "email" not in lowered:
        raise ValueError("Ce CSV n'a pas de colonne « email ».")
    # Les colonnes connues sont reconnues sans tenir compte de la casse.
    names = [h.lower() if h.lower() in BASE_COLUMNS else h for h in header]
    rows = []
    for record in reader:
        if not any(cell.strip() for cell in record):
            continue
        values = {names[i]: (record[i] if i < len(record) else "") for i in range(len(names))}
        email = values.pop("email", "").strip()
        if not email:
            continue
        rows.append(TrackingRow(email=email, values=values))
    return Tracking(rows, extra_columns=[n for n in names if n not in BASE_COLUMNS])


def load(path: Path) -> Tracking:
    if not path.exists():
        return Tracking()
    return parse_csv_text(decode_bytes(path.read_bytes()))


def save(
    tracking: Tracking,
    path: Path,
    retries: int = 5,
    retry_delay: float = 0.4,
    sleep=None,
) -> None:
    """Écrit le CSV de façon atomique (fichier temporaire + ``os.replace``).

    Si le fichier est verrouillé, réessaie ``retries`` fois puis lève ``CsvLockedError``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = tracking.to_csv_text().encode("utf-8-sig")
    last_error: OSError | None = None
    for attempt in range(retries + 1):
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".suivi-", suffix=".tmp", dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            return
        except PermissionError as error:
            last_error = error
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
            if attempt < retries:
                (sleep or time.sleep)(retry_delay * (attempt + 1))
    raise CsvLockedError(path) from last_error


@dataclass
class Classification:
    to_send: list[Recipient] = field(default_factory=list)  # nouvelles + erreurs à retenter
    new: list[Recipient] = field(default_factory=list)
    retry: list[Recipient] = field(default_factory=list)
    already_sent: list[Recipient] = field(default_factory=list)


def classify(recipients: Iterable[Recipient], tracking: Tracking) -> Classification:
    """Anti-doublon : une adresse « Envoyé » dans le CSV n'est jamais renvoyée."""
    result = Classification()
    for recipient in recipients:
        status = tracking.status_of(recipient.email)
        if status == STATUS_SENT:
            result.already_sent.append(recipient)
        elif status == STATUS_ERROR:
            result.retry.append(recipient)
            result.to_send.append(recipient)
        else:
            result.new.append(recipient)
            result.to_send.append(recipient)
    return result
