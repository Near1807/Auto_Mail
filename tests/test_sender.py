import threading

from fakes import FakeImapServer, FakeSmtpServer

from core import tracking as tr
from core.addresses import parse_recipients
from core.gmail import ImapSession, SmtpSession, imap_utf7_decode, imap_utf7_encode
from core.message import Draft
from core.sender import Job, SendConfig, send_test


def make_job(tmp_path, text, smtp, imap=None, label="", delay=0.0, password="secret", sleep=None):
    recipients = parse_recipients(text).recipients
    t = tr.load(tmp_path / "suivi.csv")
    to_send = tr.classify(recipients, t).to_send
    config = SendConfig(sender_email="me@gmail.com", sender_name="Moi", password=password,
                        draft=Draft(subject="Bonjour {prenom}", text="Salut {prenom}"),
                        recipients=to_send, csv_path=tmp_path / "suivi.csv", label=label, delay_seconds=delay)
    return Job(config=config, smtp_factory=smtp.factory,
               imap_factory=(imap.factory if imap else FakeImapServer().factory),
               sleep=sleep or (lambda s: None))


def test_sends_and_writes_csv_after_each_mail(tmp_path):
    smtp = FakeSmtpServer()
    snapshots = []
    smtp.on_send = lambda msg: snapshots.append(tr.load(tmp_path / "suivi.csv").counts()["sent"])
    job = make_job(tmp_path, "a@x.be\nb@x.be\nc@x.be", smtp)
    job.run()
    assert job.state == "done"
    assert smtp.recipients == ["a@x.be", "b@x.be", "c@x.be"]
    assert snapshots == [0, 1, 2]  # le CSV est à jour avant chaque envoi suivant
    assert smtp.connections == 1  # une seule connexion pour toute la campagne
    t = tr.load(tmp_path / "suivi.csv")
    assert [r.status for r in t.rows.values()] == ["Envoyé"] * 3
    assert t.rows["a@x.be"].values["objet"] == "Bonjour {prenom}"


def test_never_resends_already_sent(tmp_path):
    (tmp_path / "suivi.csv").write_text("email;status;reponse\nA@x.be;Envoyé;oui\n", encoding="utf-8")
    smtp = FakeSmtpServer()
    job = make_job(tmp_path, "a@x.be\nb@x.be", smtp)
    job.run()
    assert smtp.recipients == ["b@x.be"]
    assert tr.load(tmp_path / "suivi.csv").rows["a@x.be"].values["reponse"] == "oui"


def test_error_is_recorded_then_retried_next_time(tmp_path):
    smtp = FakeSmtpServer()
    smtp.refuse.add("bad@x.be")
    job = make_job(tmp_path, "a@x.be\nbad@x.be\nc@x.be", smtp)
    job.run()
    assert job.sent == 2 and job.errors == 1
    t = tr.load(tmp_path / "suivi.csv")
    assert t.rows["bad@x.be"].status == "Erreur"
    assert "550" in t.rows["bad@x.be"].values["erreur"]

    smtp2 = FakeSmtpServer()
    retry = make_job(tmp_path, "a@x.be\nbad@x.be\nc@x.be", smtp2)
    retry.run()
    assert smtp2.recipients == ["bad@x.be"]
    t = tr.load(tmp_path / "suivi.csv")
    assert t.rows["bad@x.be"].status == "Envoyé" and t.rows["bad@x.be"].values["erreur"] == ""


def test_reconnects_when_connection_drops(tmp_path):
    smtp = FakeSmtpServer()
    smtp.disconnect_before["b@x.be"] = True
    job = make_job(tmp_path, "a@x.be\nb@x.be\nc@x.be", smtp)
    job.run()
    assert smtp.recipients == ["a@x.be", "b@x.be", "c@x.be"]
    assert smtp.connections == 2


def test_bad_password_fails_without_sending(tmp_path):
    smtp = FakeSmtpServer()
    job = make_job(tmp_path, "a@x.be", smtp, password="wrong")
    job.run()
    assert job.state == "failed" and smtp.sent == []
    assert job.events[-1]["type"] == "done" and not job.events[-1]["ok"]
    assert "mot de passe" in job.events[-1]["message"]


def test_variables_from_table(tmp_path):
    smtp = FakeSmtpServer()
    job = make_job(tmp_path, "email\tprenom\na@x.be\tJean\nb@x.be\tMarie", smtp)
    job.run()
    assert [m["Subject"] for m in smtp.sent] == ["Bonjour Jean", "Bonjour Marie"]
    assert tr.load(tmp_path / "suivi.csv").rows["b@x.be"].values["objet"] == "Bonjour Marie"


def test_locked_csv_warns_and_keeps_sending(tmp_path, monkeypatch):
    real_replace = tr.os.replace
    locked = {"on": False}

    def maybe_locked(src, dst):
        if locked["on"] and str(dst).endswith("suivi.csv"):
            raise PermissionError("Excel")
        real_replace(src, dst)

    monkeypatch.setattr(tr.os, "replace", maybe_locked)
    smtp = FakeSmtpServer()
    smtp.on_send = lambda msg: locked.update(on=msg["To"] == "b@x.be")
    job = make_job(tmp_path, "a@x.be\nb@x.be\nc@x.be", smtp)
    job.run()
    assert smtp.recipients == ["a@x.be", "b@x.be", "c@x.be"]
    codes = [e.get("code") for e in job.events if e["type"] == "warning"]
    assert codes == ["csv_locked", "csv_unlocked"]
    assert len(tr.load(tmp_path / "suivi.csv").rows) == 3


def test_csv_still_locked_at_end_writes_backup(tmp_path, monkeypatch):
    real_replace = tr.os.replace

    def locked(src, dst):
        if str(dst).endswith("suivi.csv"):
            raise PermissionError("Excel")
        real_replace(src, dst)

    monkeypatch.setattr(tr.os, "replace", locked)
    job = make_job(tmp_path, "a@x.be", FakeSmtpServer())
    job.run()
    backups = list(tmp_path.glob("suivi-recupere-*.csv"))
    assert len(backups) == 1 and tr.load(backups[0]).is_sent("a@x.be")
    assert any(e.get("code") == "csv_backup" for e in job.events)


def test_pause_resume_cancel(tmp_path):
    smtp = FakeSmtpServer()
    gate = threading.Event()
    reached = threading.Event()

    def on_send(msg):
        if msg["To"] == "b@x.be":
            reached.set()
            gate.wait(5)

    smtp.on_send = on_send
    job = make_job(tmp_path, "a@x.be\nb@x.be\nc@x.be\nd@x.be", smtp)
    job.start()
    assert reached.wait(5)
    job.pause()
    gate.set()
    # En pause : rien ne part après b.
    import time
    time.sleep(0.5)
    assert smtp.recipients == ["a@x.be", "b@x.be"]
    assert job.state == "paused"
    job.cancel()
    job.join(5)
    assert job.state == "cancelled"
    assert smtp.recipients == ["a@x.be", "b@x.be"]
    t = tr.load(tmp_path / "suivi.csv")
    assert set(t.rows) == {"a@x.be", "b@x.be"}


def test_resume_continues(tmp_path):
    smtp = FakeSmtpServer()
    job = make_job(tmp_path, "a@x.be\nb@x.be", smtp)
    job.state = "running"
    job.pause()
    job.start()
    import time
    time.sleep(0.3)
    assert smtp.recipients == []
    job.resume()
    job.join(5)
    assert job.state == "done" and smtp.recipients == ["a@x.be", "b@x.be"]


def test_delay_between_mails(tmp_path):
    slept = []
    job = make_job(tmp_path, "a@x.be\nb@x.be\nc@x.be", FakeSmtpServer(), delay=1.0, sleep=slept.append)
    job.run()
    assert round(sum(slept), 3) == 2.0  # deux délais pour trois mails


def test_label_is_created_and_applied(tmp_path):
    smtp, imap = FakeSmtpServer(), FakeImapServer()
    smtp.on_send = imap.record_sent
    imap.index_delay = {}
    job = make_job(tmp_path, "a@x.be\nb@x.be", smtp, imap=imap, label="Scouts/Hikes 2026")
    job.run()
    assert imap.created == ["Scouts", "Scouts/Hikes 2026"]
    assert all("Scouts/Hikes 2026" in m["labels"] for m in imap.messages)
    label_event = next(e for e in job.events if e["type"] == "label")
    assert label_event["ok"] and label_event["count"] == 2


def test_label_waits_for_gmail_indexing(tmp_path):
    smtp, imap = FakeSmtpServer(), FakeImapServer()
    smtp.on_send = imap.record_sent
    job = make_job(tmp_path, "a@x.be", smtp, imap=imap, label="L")
    original = imap.record_sent

    def delayed(msg):
        original(msg)
        imap.index_delay[msg["Message-ID"]] = 2

    smtp.on_send = delayed
    job.run()
    assert "L" in imap.messages[0]["labels"]
    assert imap.noops == 2


def test_send_test_goes_to_myself_and_is_not_tracked(tmp_path):
    smtp = FakeSmtpServer()
    recipients = parse_recipients("email\tprenom\na@x.be\tJean").recipients
    config = SendConfig(sender_email="me@gmail.com", sender_name="", password="secret",
                        draft=Draft(subject="Hello {prenom}", text="x"), recipients=recipients,
                        csv_path=tmp_path / "suivi.csv")
    send_test(config, smtp_factory=smtp.factory)
    assert smtp.recipients == ["me@gmail.com"]
    assert smtp.sent[0]["Subject"] == "[TEST] Hello Jean"
    assert not (tmp_path / "suivi.csv").exists()


def test_find_replies():
    imap = FakeImapServer()
    imap.add("<1@gmail.com>", "Moi <me@gmail.com>", "a@x.be", thread="11", labels={"Hikes"})
    imap.add("<2@x.be>", "A <a@x.be>", "me@gmail.com", thread="11", date="Tue, 20 Oct 2026 09:30:00 +0000")
    imap.add("<3@gmail.com>", "me@gmail.com", "b@x.be", thread="12", labels={"Hikes"})
    imap.add("<4@gmail.com>", "me@gmail.com", "c@x.be", thread="13", labels={"Hikes"})
    imap.add("<5@other.be>", "Secrétariat <secretariat@x.be>", "me@gmail.com", thread="13",
             date="Wed, 21 Oct 2026 12:00:00 +0000")
    with ImapSession("me@gmail.com", "secret", factory=imap.factory) as session:
        replies = session.find_replies("Hikes")
    assert set(replies) == {"a@x.be", "c@x.be"}
    assert replies["a@x.be"].date().isoformat() == "2026-10-20"


def test_imap_utf7_roundtrip():
    for name in ["Envoyés", "Été & co", "Hikes-2026/Écoles"]:
        assert imap_utf7_decode(imap_utf7_encode(name)) == name
    assert imap_utf7_encode("Envoyés") == "Envoy&AOk-s"


def test_smtp_session_context(tmp_path):
    smtp = FakeSmtpServer()
    with SmtpSession("me@gmail.com", "secret", factory=smtp.factory):
        pass
    assert smtp.logins == 1
