"""Où vivent les données : ``%APPDATA%\\AutoMail`` sous Windows, jamais à côté de l'exe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AutoMail"


def data_dir() -> Path:
    """Dossier racine des données. ``AUTOMAIL_DATA_DIR`` le remplace (tests, dev)."""
    override = os.environ.get("AUTOMAIL_DATA_DIR")
    if override:
        root = Path(override)
    elif sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def campaigns_dir() -> Path:
    path = data_dir() / "campagnes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return data_dir() / "settings.json"
