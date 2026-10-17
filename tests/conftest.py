import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Aucune connexion sortante pendant les tests, et données dans un dossier jetable."""

    def guard(*args, **kwargs):
        raise RuntimeError("Accès réseau interdit pendant les tests")

    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr("smtplib.SMTP.connect", guard)
    monkeypatch.setenv("AUTOMAIL_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def no_sleep():
    return lambda seconds: None
