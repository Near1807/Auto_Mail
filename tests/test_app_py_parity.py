"""Cas gérés par l'ancienne appli Streamlit (app.py) que core/ doit couvrir aussi."""

import json

from fakes import FakeImapServer, FakeSmtpServer
from test_campaigns import MemoryKeyring

from core import tracking as tr
from core.addresses import parse_recipients
from core.campaigns import CampaignStore
from core.gmail import ImapSession
from core.settings import PasswordStore, load_settings, migrate_legacy_password
from test_sender import make_job


def test_row_of_addresses_copied_across_excel_columns():
    # app.py découpait aussi sur les tabulations : une ligne d'Excel copiée en largeur.
    result = parse_recipients("a@x.be\tb@x.be\tc@x.be\nd@x.be\te@x.be")
    assert [r.email for r in result.recipients] == ["a@x.be", "b@x.be", "c@x.be", "d@x.be", "e@x.be"]
    assert result.columns == []


def test_long_error_is_truncated_like_app_py():
    t = tr.Tracking()
    t.mark_error("a@x.be", "s", "x" * 500)
    assert len(t.rows["a@x.be"].values["erreur"]) == 200


def test_new_campaign_label_defaults_to_its_name(tmp_path):
    # app.py : libellé activé par défaut, au nom de la campagne.
    assert CampaignStore(tmp_path).create("Hikes 2026").draft.label == "Hikes 2026"


def test_label_reports_messages_missing_from_sent(tmp_path):
    smtp, imap = FakeSmtpServer(), FakeImapServer()

    def never_indexed(msg):
        imap.record_sent(msg)
        imap.index_delay[msg["Message-ID"]] = 99

    smtp.on_send = never_indexed
    job = make_job(tmp_path, "a@x.be", smtp, imap=imap, label="L")
    job.run()
    event = next(e for e in job.events if e["type"] == "label")
    assert not event["ok"] and event["missing"] == 1 and "introuvable" in event["message"]


def test_apply_label_returns_done_and_missing():
    imap = FakeImapServer()
    imap.add("<1@gmail.com>", "me@gmail.com", "a@x.be", thread="1")
    with ImapSession("me@gmail.com", "secret", factory=imap.factory) as session:
        assert session.apply_label(["<1@gmail.com>", "<absent@gmail.com>"], "L", sleep=lambda s: None) == (1, 1)


def test_settings_json_from_app_py_is_migrated(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"email": "me@gmail.com", "name": "Thomas", "app_password": "abcd efgh ijkl mnop",
                                "last_campaign": "Hikes"}), encoding="utf-8")
    ring = MemoryKeyring()
    assert migrate_legacy_password(path, PasswordStore(ring)) is True
    assert PasswordStore(ring).get("me@gmail.com") == "abcdefghijklmnop"
    assert "app_password" not in path.read_text(encoding="utf-8")
    assert load_settings(path).display_name == "Thomas"
    assert migrate_legacy_password(path, PasswordStore(ring)) is False


def test_csv_written_by_app_py_is_read(tmp_path):
    path = tmp_path / "Hikes.csv"
    path.write_bytes("﻿email;status;reponse;date;objet;erreur;notes\r\n"
                     "a@x.be;Envoyé;;2026-10-01 10:00;Objet;;rappeler\r\n"
                     "b@x.be;Erreur;;2026-10-01 10:01;Objet;(550, b'No such user');\r\n".encode("utf-8"))
    t = tr.load(path)
    c = tr.classify(parse_recipients("a@x.be b@x.be").recipients, t)
    assert [r.email for r in c.already_sent] == ["a@x.be"] and [r.email for r in c.retry] == ["b@x.be"]
    assert t.extra_columns == ["notes"]
