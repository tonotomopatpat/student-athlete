import json

from app.datasets import corpus
from app.datasets.cnxml import convert_module
from app.datasets.treebank import read_conllu

CNXML = b"""<document xmlns="http://cnx.rice.edu/cnxml"><title>What Is Psychology?</title>
<metadata xmlns:md="http://cnx.rice.edu/mdml"><md:title>What Is Psychology?</md:title></metadata>
<content>
<para id="p1"><term id="t1">Psychology</term> refers to the scientific study of the mind and behavior.</para>
<section id="s1"><title>Why Study Psychology?</title>
<list id="l1"><item>critical thinking</item><item>use of the <emphasis>scientific</emphasis> method</item></list>
<note class="psychology link-to-learning"><para id="p2">Watch a video.</para></note>
<figure id="f1"><media alt="x"><image src="a.jpg"/></media></figure>
</section>
<section id="s2" class="review-questions"><title>Review Questions</title><exercise><problem><para>Which?</para></problem></exercise></section>
</content>
<glossary><definition id="d1"><term>psychology</term><meaning>scientific study of the mind and behavior</meaning></definition></glossary>
</document>"""

CONLLU = """# sent_id = 1
1\tCells\tcell\tNOUN\tNNS\t_\t2\tnsubj\t_\t_
2-3\tdon't\t_\t_\t_\t_\t_\t_\t_\t_
2\tdo\tdo\tAUX\tVBP\t_\t0\troot\t_\t_
3\tn't\tnot\tPART\tRB\t_\t2\tadvmod\t_\t_
4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_

# sent_id = 2
1\t_\t_\tPRON\tPRP\t_\t0\troot\t_\t_

"""


def test_cnxml_to_markup_terms_and_glossary():
    record = convert_module(CNXML)
    assert record["title"] == "What Is Psychology?"
    assert record["markup"].rstrip("\n").split("\n\n") == [
        "# What Is Psychology?",
        "**Psychology** refers to the scientific study of the mind and behavior.",
        "## Why Study Psychology?",
        "- critical thinking",
        "- use of the scientific method",
    ]
    assert record["terms"] == ["Psychology"]
    assert record["glossary"] == [{"term": "psychology", "meaning": "scientific study of the mind and behavior"}]


def test_conllu_reader_skips_ranges_and_redacted_sentences(tmp_path):
    path = tmp_path / "x.conllu"
    path.write_text(CONLLU)
    assert list(read_conllu(path)) == [(["Cells", "do", "n't", "."], ["NOUN", "AUX", "PART", "PUNCT"])]


def test_gold_lessons_are_excluded_from_corpus(tmp_path):
    gold_lesson = ("Photosynthesis is the process by which green plants convert light energy into chemical energy "
                   "stored in glucose molecules inside the chloroplasts of leaf cells")
    other = "Basketball is a team sport in which two teams of five players try to score by shooting a ball through a hoop"
    (tmp_path / "openstax").mkdir()
    rows = [
        {"id": "a", "markup": gold_lesson},
        {"id": "b", "markup": f"{other}\n\n{gold_lesson}\n\n{other} again with more words for the count"},
        {"id": "c", "markup": other},
    ]
    (tmp_path / "openstax" / "book.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    exclusions = corpus.compute_exclusions([gold_lesson], tmp_path)
    assert exclusions["documents"] == ["a", "b"]
    kept = {doc["id"]: doc["markup"] for doc in corpus.documents(tmp_path, exclusions)}
    assert "a" not in kept and kept["c"] == other
    assert all("chloroplasts" not in text for text in kept.values())
    assert corpus.compute_exclusions([], tmp_path)["documents"] == []
