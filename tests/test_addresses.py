from core.addresses import parse_recipients, variable_name


def emails(result):
    return [r.email for r in result.recipients]


def test_one_per_line_and_separators():
    text = "a@b.be\nC@D.be, e@f.com ; g@h.org\n\n  i@j.fr  "
    assert emails(parse_recipients(text)) == ["a@b.be", "c@d.be", "e@f.com", "g@h.org", "i@j.fr"]


def test_python_list_like_the_old_script():
    text = "['j.thirion@adm.arolln.be', 'fondamental@arolln.be', \"secretariat@arolln.be\"]"
    assert emails(parse_recipients(text)) == [
        "j.thirion@adm.arolln.be", "fondamental@arolln.be", "secretariat@arolln.be"]


def test_name_with_brackets_and_mailto():
    text = 'Jean Dupont <jean@dupont.be>\n"Dupont, Marie" <marie@dupont.be>\nmailto:info@ecole.be?subject=x'
    result = parse_recipients(text)
    assert emails(result) == ["jean@dupont.be", "marie@dupont.be", "info@ecole.be"]
    assert result.invalid == []


def test_invalid_and_duplicates_are_reported():
    result = parse_recipients("a@b.be\npas-une-adresse\nx@y\nA@B.be\nfoo@@bar.com")
    assert emails(result) == ["a@b.be"]
    assert result.invalid == ["pas-une-adresse", "x@y", "foo@@bar.com"]
    assert result.duplicates == ["a@b.be"]


def test_trailing_dot_and_spaces_are_cleaned():
    assert emails(parse_recipients("  Contact : info@school.be.  ")) == ["info@school.be"]


def test_excel_table_with_header_gives_variables():
    text = "Prénom\tNom\tE-mail\tÉcole\nJean\tDupont\tjean@d.be\tLa Croix\nMarie\tMartin\tmarie@m.be\tBlocry\n"
    result = parse_recipients(text)
    assert emails(result) == ["jean@d.be", "marie@m.be"]
    assert result.columns == ["prenom", "nom", "ecole"]
    assert result.recipients[0].fields == {"prenom": "Jean", "nom": "Dupont", "ecole": "La Croix"}


def test_excel_table_without_header():
    text = "jean@d.be\tJean\nmarie@m.be\tMarie\n"
    result = parse_recipients(text)
    assert emails(result) == ["jean@d.be", "marie@m.be"]
    assert result.recipients[1].fields == {"colonne2": "Marie"}


def test_table_row_with_bad_email_is_invalid():
    result = parse_recipients("email\tprenom\nok@x.be\tA\nnope\tB\n")
    assert emails(result) == ["ok@x.be"]
    assert result.invalid == ["nope"]


def test_empty_input():
    result = parse_recipients("   \n ")
    assert result.recipients == [] and result.invalid == []


def test_variable_name():
    assert variable_name("Prénom") == "prenom"
    assert variable_name("Nom de l'école") == "nom_de_l_ecole"
