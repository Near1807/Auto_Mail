from fakes import parse

from core.message import Draft, build_message, html_to_text, render, used_variables


def test_render_variables_and_unknown_left_alone():
    assert render("Bonjour {prenom} {Nom}, {inconnu}", {"prenom": "Jean", "nom": "Dupont"}) == \
        "Bonjour Jean Dupont, {inconnu}"


def test_render_escapes_html_values():
    assert render("<b>{nom}</b>", {"nom": "<Tom & Co>"}, escape=True) == "<b>&lt;Tom &amp; Co&gt;</b>"


def test_used_variables():
    assert used_variables("Hi {prenom}", "<p>{ecole}</p>") == {"prenom", "ecole"}


def test_html_to_text():
    source = ("<style>p{color:red}</style><h1>Titre</h1><p>Bonjour <b>Jean</b>,<br>ligne 2</p>"
              "<ul><li>un</li><li>deux</li></ul><p><a href='https://x.be'>site</a></p>")
    text = html_to_text(source)
    assert "color" not in text
    assert "Titre\n\nBonjour Jean,\nligne 2" in text
    assert "- un\n- deux" in text
    assert "site (https://x.be)" in text


def test_text_message():
    msg = build_message(Draft(subject="Salut {prenom}", text="Bonjour {prenom}"), "me@gmail.com", "Thomas",
                        "a@b.be", {"prenom": "Jean"})
    parsed = parse(msg)
    assert parsed["Subject"] == "Salut Jean"
    assert parsed["From"] == "Thomas <me@gmail.com>"
    assert parsed["Message-ID"].endswith("@gmail.com>")
    assert parsed.get_content_type() == "text/plain"
    assert parsed.get_payload(decode=True).decode().strip() == "Bonjour Jean"


def test_html_message_is_multipart_with_attachment(tmp_path):
    pdf = tmp_path / "CV Thomas.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    draft = Draft(subject="S", mode="html", html="<p>Bonjour <b>{prenom}</b></p>", attachments=[pdf])
    msg = parse(build_message(draft, "me@gmail.com", "", "a@b.be", {"prenom": "Jean"}))
    assert msg.get_content_type() == "multipart/mixed"
    alt = msg.get_payload()[0]
    assert alt.get_content_type() == "multipart/alternative"
    plain, html = alt.get_payload()
    assert plain.get_payload(decode=True).decode().strip() == "Bonjour Jean"
    assert "<b>Jean</b>" in html.get_payload(decode=True).decode()
    attachment = msg.get_payload()[1]
    assert attachment.get_filename() == "CV Thomas.pdf"
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_payload(decode=True) == b"%PDF-1.4 fake"
