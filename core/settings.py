"""Réglages (``settings.json``, sans mot de passe) et mot de passe (keyring).

Sous Windows, ``keyring`` range le mot de passe d'application dans le Gestionnaire
d'identification Windows. Il n'est jamais écrit dans un fichier.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

KEYRING_SERVICE = "AutoMail"


@dataclass
class Settings:
    email: str = ""
    display_name: str = ""
    delay_seconds: float = 3.0
    theme: str = "system"  # system | light | dark

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = set(cls.__dataclass_fields__)
        values = {k: v for k, v in data.items() if k in known}
        if "name" in data and "display_name" not in data:  # clé utilisée par app.py
            values["display_name"] = data["name"]
        return cls(**values)


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings, path: Path) -> None:
    data = asdict(settings)
    data.pop("password", None)  # ceinture et bretelles : jamais de mot de passe ici
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class PasswordStore:
    """Fine enveloppe autour de ``keyring`` (remplaçable dans les tests)."""

    def __init__(self, backend=None):
        if backend is None:
            import keyring

            backend = keyring
        self.backend = backend

    def get(self, email: str) -> str:
        if not email:
            return ""
        try:
            return self.backend.get_password(KEYRING_SERVICE, email.lower()) or ""
        except Exception:
            return ""

    def set(self, email: str, password: str) -> None:
        # Gmail affiche le mot de passe d'application par groupes de 4 : on enlève les espaces.
        self.backend.set_password(KEYRING_SERVICE, email.lower(), password.replace(" ", ""))

    def delete(self, email: str) -> None:
        try:
            self.backend.delete_password(KEYRING_SERVICE, email.lower())
        except Exception:
            pass


def migrate_legacy_password(path: Path, passwords: "PasswordStore") -> bool:
    """app.py gardait ``app_password`` en clair dans settings.json : on le range dans
    keyring et on réécrit le fichier sans lui. Retourne True si une migration a eu lieu."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict) or "app_password" not in data:
        return False
    settings = Settings.from_dict(data)
    password = str(data.get("app_password") or "")
    if password and settings.email:
        passwords.set(settings.email, password)
    save_settings(settings, path)
    return True
