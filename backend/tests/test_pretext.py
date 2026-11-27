from app.datasets.pretext import plain_paragraphs, source_of


def test_plain_paragraphs_strips_markup():
    markup = "# Cells\n\n- The **nucleus** holds DNA.\n| a | b |\n\nPlain   text  here."
    assert plain_paragraphs(markup) == ["Cells", "The nucleus holds DNA.", "Plain text here."]


def test_source_of_uses_id_prefix():
    assert source_of("openstax:biology-2e:m1") == "openstax"
    assert source_of("wiki-en:12") == "wiki-en"
