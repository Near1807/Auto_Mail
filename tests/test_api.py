import time

import pytest
from fastapi.testclient import TestClient
from fakes import FakeImapServer, FakeSmtpServer
from test_campaigns import MemoryKeyring

from api.app import create_app
from core import paths
from core import tracking as tr
from core.settings import PasswordStore


@pytest.fixture
def env():
    smtp, imap = FakeSmtpServer(), FakeImapServer()
    smtp.on_send = imap.record_sent
    opened = []
    app = create_app(smtp_factory=smtp.factory, imap_factory=imap.factory,
                     passwords=PasswordStore(MemoryKeyring()), opener=opened.append, serve_static=False)
    client = TestClient(app)
    client.put("/api/settings", json={"email": "me@gmail.com", "display_name": "Moi", "delay_seconds": 0})
    client.put("/api/account/password", json={"password": "secret"})
    return client, smtp, imap, opened


def wait_job(client, job_id):
    for _ in range(200):
        snap = client.get("/api/jobs/current").json()
        if snap["id"] == job_id and snap["state"] in ("done", "failed", "cancelled"):
            return snap
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_settings_never_store_password(env):
    client, *_ = env
    s = client.get("/api/settings").json()
    assert s["has_password"] is True and "password" not in s
    assert "secret" not in paths.settings_file().read_text(encoding="utf-8")


def test_connection_test(env):
    client, *_ = env
    assert client.post("/api/account/test", json={}).json()["ok"] is True
    bad = client.post("/api/account/test", json={"password": "nope"}).json()
    assert bad["ok"] is False and "mot de passe" in bad["message"]


def test_full_campaign_flow(env):
    client, smtp, imap, opened = env
    c = client.post("/api/campaigns", json={"name": "Hikes 2026"}).json()
    cid = c["id"]
    client.put(f"/api/campaigns/{cid}/draft", json={
        "subject": "Bonjour {prenom}", "mode": "html", "html": "<p>Salut {prenom}</p>",
        "recipients_raw": "email\tprenom\na@x.be\tJean\nb@x.be\tMarie\nnope\tX", "label": "Hikes"})
    client.post(f"/api/campaigns/{cid}/attachments", files=[("files", ("cv.pdf", b"%PDF", "application/pdf"))])

    analysis = client.post(f"/api/campaigns/{cid}/analyze", json={}).json()
    assert analysis["counts"]["to_send"] == 2 and analysis["invalid"] == ["nope"]
    assert analysis["columns"] == ["prenom"]

    summary = client.get(f"/api/campaigns/{cid}/send-summary").json()
    assert summary["count"] == 2 and summary["label"] == "Hikes" and summary["attachments"][0]["name"] == "cv.pdf"

    assert client.post(f"/api/campaigns/{cid}/test-send").json()["ok"]
    assert smtp.recipients == ["me@gmail.com"]

    job = client.post(f"/api/campaigns/{cid}/send").json()
    done = wait_job(client, job["id"])
    assert done["state"] == "done" and done["sent"] == 2
    assert smtp.recipients[1:] == ["a@x.be", "b@x.be"]

    with client.stream("GET", f"/api/jobs/{job['id']}/events") as stream:
        body = "".join(stream.iter_text())
    assert '"type": "sent"' in body and '"type": "label"' in body and '"type": "done"' in body

    # Relancer : plus rien à envoyer.
    again = client.post(f"/api/campaigns/{cid}/analyze", json={}).json()
    assert again["counts"]["already_sent"] == 2 and again["counts"]["to_send"] == 0
    assert client.post(f"/api/campaigns/{cid}/send").status_code == 400

    tracking = client.get(f"/api/campaigns/{cid}/tracking").json()
    assert tracking["counts"]["sent"] == 2
    assert tracking["columns"] == ["email", "status", "reponse", "date", "objet", "erreur"]

    assert client.patch(f"/api/campaigns/{cid}/tracking",
                        json={"email": "a@x.be", "value": "Oui !"}).json()["counts"]["replies"] == 1

    # Réponse de Marie dans le fil → remplie automatiquement.
    b_thread = next(m["thread"] for m in imap.messages if m["to"] == "b@x.be")
    imap.add("<r@x.be>", "Marie <b@x.be>", "me@gmail.com", thread=b_thread, date="Tue, 20 Oct 2026 09:00:00 +0000")
    replies = client.post(f"/api/campaigns/{cid}/check-replies").json()
    assert replies["updated"] == ["b@x.be"]
    rows = {r["email"]: r for r in client.get(f"/api/campaigns/{cid}/tracking").json()["rows"]}
    assert rows["b@x.be"]["reponse"] == "Répondu le 2026-10-20"
    assert rows["a@x.be"]["reponse"] == "Oui !"  # jamais écrasé

    export = client.get(f"/api/campaigns/{cid}/export")
    assert export.content.startswith(b"\xef\xbb\xbf")

    client.post(f"/api/campaigns/{cid}/open-folder")
    assert opened and opened[0].name == cid


def test_import_rename_delete(env):
    client, *_ = env
    r = client.post("/api/campaigns/import",
                    files={"file": ("suivi_envois.csv", "email;status;reponse\na@b.be;Envoyé;\n".encode(), "text/csv")})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["counts"]["sent"] == 1
    renamed = client.patch(f"/api/campaigns/{cid}", json={"name": "Hikes"}).json()
    assert renamed["id"] == "hikes" and renamed["name"] == "Hikes"
    assert client.delete("/api/campaigns/hikes").status_code == 204
    assert client.get("/api/campaigns").json() == []


def test_bad_import(env):
    client, *_ = env
    r = client.post("/api/campaigns/import", files={"file": ("x.csv", b"foo;bar\n1;2\n", "text/csv")})
    assert r.status_code == 400


def test_send_requires_password(env):
    client, *_ = env
    client.put("/api/account/password", json={"password": ""})
    cid = client.post("/api/campaigns", json={"name": "A"}).json()["id"]
    client.put(f"/api/campaigns/{cid}/draft", json={"subject": "s", "text": "t", "recipients_raw": "a@x.be"})
    r = client.post(f"/api/campaigns/{cid}/send")
    assert r.status_code == 400 and "mot de passe" in r.json()["detail"]


def test_locked_csv_returns_423(env, monkeypatch):
    client, *_ = env
    cid = client.post("/api/campaigns/import",
                      files={"file": ("a.csv", b"email;status;reponse\na@b.be;Envoy\xc3\xa9;\n", "text/csv")}).json()["id"]

    def locked(src, dst):
        raise PermissionError()

    monkeypatch.setattr(tr.os, "replace", locked)
    monkeypatch.setattr(tr.time, "sleep", lambda s: None)
    r = client.patch(f"/api/campaigns/{cid}/tracking", json={"email": "a@b.be", "value": "x"})
    assert r.status_code == 423 and "Excel" in r.json()["detail"]
