"""Lecture des destinataires collés dans n'importe quel format.

Formats acceptés, mélangeables :

- une adresse par ligne, ou séparées par ``,`` / ``;`` / espaces ;
- une liste Python : ``['a@b.be', "c@d.be"]`` ;
- ``Nom Prénom <a@b.be>`` et ``mailto:a@b.be`` ;
- un tableau copié d'Excel (colonnes séparées par des tabulations) dont une colonne
  contient les adresses ; si la première ligne est un en-tête, ses colonnes deviennent
  des variables (``{prenom}``, ``{nom}``…).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Volontairement strict sur la forme, sans prétendre valider le RFC 5322 entier.
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)
_HEADER_WORDS = {"email", "e-mail", "mail", "courriel", "adresse", "adresse email", "adresse mail"}
_STRIP_CHARS = " \t\r\n\"'`()[]{}<>,;:"


@dataclass
class Recipient:
    email: str  # normalisée : minuscules, sans espaces
    fields: dict[str, str] = field(default_factory=dict)  # variables issues du tableau


@dataclass
class ParseResult:
    recipients: list[Recipient] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)  # noms de variables disponibles


def normalize_email(value: str) -> str:
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value)) and ".." not in value


def variable_name(header: str) -> str:
    """``"Prénom"`` → ``prenom`` ; ``"Nom de l'école"`` → ``nom_de_l_ecole``."""
    text = unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text or "colonne"


def _clean_candidate(token: str) -> str:
    token = token.strip(_STRIP_CHARS)
    if token.lower().startswith("mailto:"):
        token = token[7:]
        token = token.split("?", 1)[0]
    return token.strip(_STRIP_CHARS).rstrip(".")


def _emails_in_chunk(chunk: str) -> tuple[list[str], list[str]]:
    """Adresses (valides, invalides) d'un morceau de texte sans séparateur de liste."""
    chunk = chunk.strip(_STRIP_CHARS)
    if not chunk:
        return [], []
    # "Nom <adresse>" : seule l'adresse entre chevrons compte.
    bracketed = re.findall(r"<([^<>]*)>", chunk)
    candidates = bracketed or [t for t in re.split(r"\s+", chunk) if "@" in t]
    if not candidates:
        return [], [chunk]
    valid, invalid = [], []
    for raw in candidates:
        cleaned = _clean_candidate(raw)
        if is_valid_email(cleaned):
            valid.append(normalize_email(cleaned))
        elif cleaned:
            invalid.append(cleaned)
    return valid, invalid


def _parse_free_text(text: str) -> tuple[list[Recipient], list[str]]:
    recipients: list[Recipient] = []
    invalid: list[str] = []
    for line in text.splitlines():
        # Les guillemets protègent les virgules d'un nom : "Dupont, Jean" <j@d.be>
        for chunk in re.split(r"[,;](?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", line):
            valid, bad = _emails_in_chunk(chunk)
            recipients.extend(Recipient(email=e) for e in valid)
            invalid.extend(bad)
    return recipients, invalid


def _looks_like_table(lines: list[str]) -> bool:
    return sum(1 for line in lines if "\t" in line) >= max(1, len(lines) // 2)


def _parse_table(lines: list[str]) -> tuple[list[Recipient], list[str], list[str]]:
    rows = [[cell.strip() for cell in line.split("\t")] for line in lines]
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    def email_score(col: int, body: list[list[str]]) -> int:
        return sum(1 for r in body if is_valid_email(_clean_candidate(r[col])))

    first = rows[0]
    has_header = not any("@" in cell for cell in first)
    body = rows[1:] if has_header else rows
    email_col = max(range(width), key=lambda c: email_score(c, body)) if body else 0
    if has_header:
        for c, cell in enumerate(first):
            if cell.strip().lower() in _HEADER_WORDS and email_score(c, body):
                email_col = c
                break

    columns: list[str] = []
    if has_header:
        seen: set[str] = set()
        for c, cell in enumerate(first):
            name = variable_name(cell) if cell else f"colonne{c + 1}"
            if c == email_col:
                name = "email"
            base, n = name, 2
            while name in seen:
                name, n = f"{base}_{n}", n + 1
            seen.add(name)
            columns.append(name)
    else:
        columns = [f"colonne{c + 1}" if c != email_col else "email" for c in range(width)]

    recipients, invalid = [], []
    for row in body:
        if not any(row):
            continue
        cleaned = _clean_candidate(row[email_col])
        if not is_valid_email(cleaned):
            invalid.append(row[email_col] or " | ".join(c for c in row if c))
            continue
        fields = {columns[c]: row[c] for c in range(width) if c != email_col}
        recipients.append(Recipient(email=normalize_email(cleaned), fields=fields))
    return recipients, invalid, [c for c in columns if c != "email"]


def parse_recipients(text: str) -> ParseResult:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ParseResult()
    if _looks_like_table(lines):
        found, invalid, columns = _parse_table(lines)
    else:
        found, invalid = _parse_free_text("\n".join(lines))
        columns = []

    result = ParseResult(invalid=invalid, columns=columns)
    seen: set[str] = set()
    for recipient in found:
        if recipient.email in seen:
            result.duplicates.append(recipient.email)
            continue
        seen.add(recipient.email)
        result.recipients.append(recipient)
    return result
