"""Compatibilité des données : les fichiers écrits par Auto Mail 1.0.0 restent lus à l'identique.

Les fichiers de ``tests/fixtures/v1.0.0`` reproduisent exactement ce que la version 1.0.0
écrit dans ``%APPDATA%\\AutoMail`` (chemins, noms, format CSV, brouillon, réglages).
Si un de ces tests casse, une mise à jour rendrait les données existantes illisibles.
"""

import shutil
from pathlib import Path

from core import paths
from core import tracking as tr
from core.addresses import parse_recipients
from core.campaigns import ATTACHMENTS_DIR, CSV_NAME, DRAFT_NAME, CampaignStore
from core.settings import KEYRING_SERVICE, PasswordStore, load_settings, save_settings
from test_campaigns import MemoryKeyring

FIXTURES = Path(__file__).parent / "fixtures" / "v1.0.0"


def install_fixtures(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "AutoMail"
    shutil.copytree(FIXTURES, data)
    monkeypatch.setenv("AUTOMAIL_DATA_DIR", str(data))
    return data


def test_paths_and_file_names_are_unchanged(tmp_path, monkeypatch):
    data = install_fixtures(tmp_path, monkeypatch)
    assert paths.APP_NAME == "AutoMail"
    assert paths.campaigns_dir() == data / "campagnes"
    assert paths.settings_file() == data / "settings.json"
    assert (CSV_NAME, DRAFT_NAME, ATTACHMENTS_DIR) == ("suivi.csv", "message.json", "pj")


def test_windows_data_dir_is_appdata_automail(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTOMAIL_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert paths.data_dir() == tmp_path / "Roaming" / "AutoMail"


def test_tracking_csv_is_read_identically(tmp_path, monkeypatch):
    data = install_fixtures(tmp_path, monkeypatch)
    path = data / "campagnes" / "hikes-2026-2027" / "suivi.csv"
    t = tr.load(path)
    assert t.columns == ["email", "status", "reponse", "date", "objet", "erreur", "notes"]
    assert list(t.rows) == ["ann@exemple.be", "bob@exemple.be", "cid@exemple.be"]
    ann = t.rows["ann@exemple.be"].values
    assert ann == {"status": "Envoyé", "reponse": "Répondu le 2026-10-20", "date": "2026-10-18 09:12",
                   "objet": "Bonjour Ann", "erreur": "", "notes": "rappeler lundi"}
    assert t.rows["bob@exemple.be"].values["erreur"] == "Adresse refusée par le serveur (550) : 5.1.1 ; inconnue"
    assert t.rows["cid@exemple.be"].values["objet"] == "Objet ; avec point-virgule"
    # Anti-doublon : les « Envoyé » du fichier ne sont jamais renvoyés, les « Erreur » sont retentés.
    c = tr.classify(parse_recipients("ann@exemple.be bob@exemple.be cid@exemple.be").recipients, t)
    assert [r.email for r in c.already_sent] == ["ann@exemple.be", "cid@exemple.be"]
    assert [r.email for r in c.retry] == ["bob@exemple.be"]


def test_tracking_csv_is_rewritten_byte_for_byte(tmp_path, monkeypatch):
    data = install_fixtures(tmp_path, monkeypatch)
    path = data / "campagnes" / "hikes-2026-2027" / "suivi.csv"
    original = path.read_bytes()
    assert original.startswith(b"\xef\xbb\xbf")  # UTF-8 avec BOM
    tr.save(tr.load(path), path)
    assert path.read_bytes() == original


def test_campaign_and_draft_are_read_identically(tmp_path, monkeypatch):
    install_fixtures(tmp_path, monkeypatch)
    store = CampaignStore(paths.campaigns_dir())
    (campaign,) = store.list()
    assert campaign.id == "hikes-2026-2027"
    d = campaign.draft
    assert (d.name, d.subject, d.mode, d.label, d.preview_email) == (
        "Hikes 2026-2027", "Bonjour {prenom}", "html", "Scouts/Hikes 2026-2027", "ann@exemple.be")
    assert d.recipients_raw == "email\tprenom\nann@exemple.be\tAnn\nbob@exemple.be\tBob"
    assert [p.name for p in campaign.attachments()] == ["CV.pdf"]
    assert campaign.summary()["counts"] == {"total": 3, "sent": 2, "errors": 1, "replies": 1}


def test_settings_are_read_and_rewritten_identically(tmp_path, monkeypatch):
    data = install_fixtures(tmp_path, monkeypatch)
    path = data / "settings.json"
    s = load_settings(path)
    assert (s.email, s.display_name, s.delay_seconds, s.theme) == ("tomtom.leman@gmail.com", "Thomas Leman", 3.0, "dark")
    original = path.read_text(encoding="utf-8")
    save_settings(s, path)
    assert path.read_text(encoding="utf-8").strip() == original.strip()


def test_keyring_service_and_key_are_unchanged():
    ring = MemoryKeyring()
    ring.set_password("AutoMail", "tomtom.leman@gmail.com", "abcdefghijklmnop")  # écrit par la 1.0.0
    assert KEYRING_SERVICE == "AutoMail"
    assert PasswordStore(ring).get("Tomtom.Leman@gmail.com") == "abcdefghijklmnop"
