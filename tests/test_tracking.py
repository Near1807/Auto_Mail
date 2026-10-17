import pytest

from core import tracking as tr
from core.addresses import parse_recipients


def test_reads_old_csv_without_bom(tmp_path):
    path = tmp_path / "suivi_envois.csv"
    # Exactement ce qu'écrivait l'ancien script : utf-8 sans BOM, 3 colonnes.
    path.write_text("email;status;reponse\r\nA@b.be;Envoyé;\r\nc@d.be;Envoyé;Oui, dispo\r\n", encoding="utf-8")
    t = tr.load(path)
    assert list(t.rows) == ["a@b.be", "c@d.be"]
    assert t.is_sent(" A@B.BE ")
    assert t.rows["c@d.be"].values["reponse"] == "Oui, dispo"


def test_reads_cp1252_csv(tmp_path):
    path = tmp_path / "old.csv"
    path.write_bytes("email;status;reponse\na@b.be;Envoyé;réponse\n".encode("cp1252"))
    t = tr.load(path)
    assert t.is_sent("a@b.be")
    assert t.rows["a@b.be"].values["reponse"] == "réponse"


def test_write_format_bom_semicolon_and_columns(tmp_path):
    path = tmp_path / "suivi.csv"
    t = tr.Tracking()
    t.mark_sent("a@b.be", "Objet ; avec point-virgule")
    tr.save(t, path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "email;status;reponse;date;objet;erreur"
    assert lines[1].startswith("a@b.be;Envoyé;;")
    assert '"Objet ; avec point-virgule"' in lines[1]
    assert tr.load(path).rows["a@b.be"].values["objet"] == "Objet ; avec point-virgule"


def test_extra_columns_are_kept(tmp_path):
    path = tmp_path / "suivi.csv"
    path.write_text("email;status;reponse;Téléphone;notes\na@b.be;Envoyé;;0475;rappeler\n", encoding="utf-8")
    t = tr.load(path)
    t.mark_sent("new@x.be", "Sujet")
    tr.save(t, path)
    again = tr.load(path)
    assert again.columns == tr.BASE_COLUMNS + ["Téléphone", "notes"]
    assert again.rows["a@b.be"].values["notes"] == "rappeler"
    assert again.rows["a@b.be"].values["Téléphone"] == "0475"


def test_classify_never_resends_sent_and_retries_errors():
    t = tr.Tracking()
    t.mark_sent("sent@x.be", "s")
    t.mark_error("err@x.be", "s", "boom")
    parsed = parse_recipients("SENT@x.be\nerr@x.be\nnew@x.be")
    c = tr.classify(parsed.recipients, t)
    assert [r.email for r in c.already_sent] == ["sent@x.be"]
    assert [r.email for r in c.retry] == ["err@x.be"]
    assert [r.email for r in c.new] == ["new@x.be"]
    assert [r.email for r in c.to_send] == ["err@x.be", "new@x.be"]


def test_duplicate_rows_in_file_sent_wins(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("email;status;reponse\na@b.be;Envoyé;\nA@b.be;Erreur;\n", encoding="utf-8")
    assert tr.load(path).is_sent("a@b.be")


def test_error_then_success_keeps_reponse():
    t = tr.Tracking()
    t.mark_error("a@b.be", "s", "boom")
    t.set_value("a@b.be", "reponse", "à rappeler")
    t.mark_sent("a@b.be", "s")
    row = t.rows["a@b.be"]
    assert row.status == "Envoyé" and row.values["erreur"] == "" and row.values["reponse"] == "à rappeler"


def test_locked_file_retries_then_raises(tmp_path, monkeypatch):
    path = tmp_path / "suivi.csv"
    calls = []

    def locked(src, dst):
        calls.append(dst)
        raise PermissionError("locked by Excel")

    monkeypatch.setattr(tr.os, "replace", locked)
    with pytest.raises(tr.CsvLockedError):
        tr.save(tr.Tracking(), path, retries=3, sleep=lambda s: None)
    assert len(calls) == 4
    assert list(tmp_path.iterdir()) == []  # pas de fichier temporaire oublié


def test_locked_file_recovers(tmp_path, monkeypatch):
    path = tmp_path / "suivi.csv"
    real = tr.os.replace
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] < 3:
            raise PermissionError("locked")
        real(src, dst)

    monkeypatch.setattr(tr.os, "replace", flaky)
    t = tr.Tracking()
    t.mark_sent("a@b.be", "s")
    tr.save(t, path, sleep=lambda s: None)
    assert tr.load(path).is_sent("a@b.be")


def test_csv_without_email_column_is_rejected():
    with pytest.raises(ValueError):
        tr.parse_csv_text("nom;statut\nx;y\n")


def test_counts():
    t = tr.Tracking()
    t.mark_sent("a@b.be", "s")
    t.mark_sent("c@b.be", "s")
    t.mark_error("d@b.be", "s", "x")
    t.set_value("a@b.be", "reponse", "oui")
    assert t.counts() == {"total": 3, "sent": 2, "errors": 1, "replies": 1}
