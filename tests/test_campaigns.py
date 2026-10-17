import json

import pytest

from core import tracking as tr
from core.campaigns import CampaignStore
from core.settings import PasswordStore, Settings, load_settings, save_settings


def test_create_list_rename_delete(tmp_path):
    store = CampaignStore(tmp_path)
    c = store.create("Hikes 2026-2027")
    assert c.id == "hikes-2026-2027"
    store.create("Hikes 2026-2027")
    assert sorted(x.id for x in store.list()) == ["hikes-2026-2027", "hikes-2026-2027-2"]
    renamed = store.rename(c.id, "Camp d'été")
    assert renamed.id == "camp-d-ete" and renamed.draft.name == "Camp d'été"
    with pytest.raises(KeyError):
        store.get("hikes-2026-2027")
    store.delete(renamed.id)
    assert [x.id for x in store.list()] == ["hikes-2026-2027-2"]


def test_draft_is_saved(tmp_path):
    store = CampaignStore(tmp_path)
    c = store.create("A")
    store.update_draft(c.id, {"subject": "Objet", "mode": "html", "html": "<p>x</p>", "name": "ignored"})
    again = store.get(c.id)
    assert again.draft.subject == "Objet" and again.draft.mode == "html" and again.draft.name == "A"
    assert json.loads((c.path / "message.json").read_text(encoding="utf-8"))["html"] == "<p>x</p>"


def test_import_old_csv_rewrites_new_format(tmp_path):
    store = CampaignStore(tmp_path)
    c = store.import_csv("Ancien", "email;status;reponse\na@b.be;Envoyé;oui\n".encode())
    raw = c.csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").splitlines()[0] == "email;status;reponse;date;objet;erreur"
    assert tr.load(c.csv_path).is_sent("a@b.be")


def test_import_bad_csv_leaves_nothing(tmp_path):
    store = CampaignStore(tmp_path)
    with pytest.raises(ValueError):
        store.import_csv("Bad", b"nom;x\n")
    assert store.list() == []


def test_attachments(tmp_path):
    store = CampaignStore(tmp_path)
    c = store.create("A")
    store.add_attachment(c.id, "cv.pdf", b"1")
    store.add_attachment(c.id, "../../cv.pdf", b"2")
    names = [p.name for p in store.get(c.id).attachments()]
    assert names == ["cv (2).pdf", "cv.pdf"]
    store.remove_attachment(c.id, "cv.pdf")
    assert [p.name for p in store.get(c.id).attachments()] == ["cv (2).pdf"]


def test_get_rejects_path_traversal(tmp_path):
    store = CampaignStore(tmp_path / "campagnes")
    with pytest.raises(KeyError):
        store.get("../etc")


class MemoryKeyring:
    def __init__(self):
        self.data = {}

    def get_password(self, service, user):
        return self.data.get((service, user))

    def set_password(self, service, user, password):
        self.data[(service, user)] = password

    def delete_password(self, service, user):
        self.data.pop((service, user))


def test_password_never_in_settings_file(tmp_path):
    ring = MemoryKeyring()
    passwords = PasswordStore(ring)
    passwords.set("Me@gmail.com", "abcd efgh ijkl mnop")
    assert passwords.get("me@gmail.com") == "abcdefghijklmnop"
    path = tmp_path / "settings.json"
    save_settings(Settings(email="me@gmail.com", display_name="Moi"), path)
    assert "abcd" not in path.read_text(encoding="utf-8")
    assert load_settings(path).display_name == "Moi"
