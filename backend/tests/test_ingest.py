import time

import pytest
from tests.ingest_fixtures import BILLION_LAUGHS, make_docx, make_pdf, make_pptx, rewrite_zip

from app.ingest.document import Block, Document, IngestError
from app.ingest.extract import extract_document, parse_file, run_isolated, truncate
from app.ingest.plain import parse_text, to_markup
from app.ingest.routing import route_sections
from app.ingest.structure import outline, split_numbering
from app.ingest.syllabus import clean_topic, propose_topics
from app.nlp.language import detect_language

LESSON = """CELL BIOLOGY

1.1 Cell Structure

The **cell membrane** controls what enters and leaves the cell. The nucleus stores
genetic informa-
tion in the form of DNA.

- Mitochondria produce ATP.
- Ribosomes build proteins.

1.2 Photosynthesis

Photosynthesis is the process by which plants convert light energy into chemical energy.
"""


def write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_plain_text_structure_and_markup_round_trip():
    document = parse_text(LESSON)
    kinds = [(block.kind, block.text[:20]) for block in document.blocks]
    assert kinds[0] == ("heading", "CELL BIOLOGY")
    assert ("heading", "1.1 Cell Structure") in kinds
    paragraph = next(block for block in document.blocks if block.text.startswith("The cell membrane"))
    assert "genetic information in the form of DNA." in paragraph.text
    assert paragraph.emphasis == ["cell membrane"]
    assert [b.text for b in document.blocks if b.kind == "list_item"] == ["Mitochondria produce ATP.", "Ribosomes build proteins."]
    again = parse_text(to_markup(document))
    assert [(b.kind, b.text, b.level, b.emphasis) for b in again.blocks] == [
        (b.kind, b.text, b.level, b.emphasis) for b in document.blocks
    ]


def test_outline_uses_numbering_for_levels():
    sections = outline(parse_text(LESSON))
    assert [(s.title, s.level, s.number) for s in sections] == [
        ("CELL BIOLOGY", 1, None),
        ("Cell Structure", 2, "1.1"),
        ("Photosynthesis", 2, "1.2"),
    ]
    assert split_numbering("Week 3: Memory") == ("Week 3", "Memory")
    assert split_numbering("Unit II - The Self") == ("Unit II", "The Self")
    assert split_numbering("2024 was a year") == (None, "2024 was a year")


def test_pdf_headings_bold_lists_and_running_heads(tmp_path):
    header = ("Arellano University - Biology 101", 9, False)
    pages = [
        [header, ("Cell Biology", 20, True), ("The cell membrane controls what enters and leaves the cell.", 11, False),
         ("It is made of a lipid bilayer.", 11, False), ("- Mitochondria produce ATP.", 11, False), ("1", 9, False)],
        [header, ("Photosynthesis", 16, False), ("Key terms", 11, True),
         ("Photosynthesis is the process by which plants convert light energy into chemical energy.", 11, False), ("2", 9, False)],
        [header, ("Respiration", 16, False), ("Cells release energy from glucose.", 11, False), ("3", 9, False)],
    ]
    document = parse_file(write(tmp_path, "lesson.pdf", make_pdf(pages)), "pdf")
    blocks = [(b.kind, b.text, b.level, b.page) for b in document.blocks]
    assert ("heading", "Cell Biology", 1, 1) in blocks
    assert ("heading", "Photosynthesis", 2, 2) in blocks
    assert ("heading", "Key terms", 3, 2) in blocks
    assert ("list_item", "Mitochondria produce ATP.", 0, 1) in blocks
    assert ("paragraph", "The cell membrane controls what enters and leaves the cell. It is made of a lipid bilayer.", 0, 1) in blocks
    assert not any("Arellano" in b.text or b.text in ("1", "2", "3") for b in document.blocks)
    assert document.warnings == []


def test_pdf_without_text_layer_is_flagged(tmp_path):
    document = parse_file(write(tmp_path, "scan.pdf", make_pdf([[], []])), "pdf")
    assert "no_text_layer" in document.warnings


def test_docx_styles_lists_bold_and_tables(tmp_path):
    def build(doc):
        doc.add_heading("Memory", level=1)
        paragraph = doc.add_paragraph("")
        paragraph.add_run("Encoding").bold = True
        paragraph.add_run(" is the first stage of memory.")
        doc.add_paragraph("Sensory memory", style="List Bullet")
        doc.add_paragraph("Short-term memory", style="List Bullet")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = "Stage", "Duration"
        table.cell(1, 0).text, table.cell(1, 1).text = "Sensory", "Under one second"

    document = parse_file(write(tmp_path, "notes.docx", make_docx(build)), "docx")
    blocks = [(b.kind, b.text) for b in document.blocks]
    assert blocks == [
        ("heading", "Memory"),
        ("paragraph", "Encoding is the first stage of memory."),
        ("list_item", "Sensory memory"),
        ("list_item", "Short-term memory"),
        ("table_row", "Stage | Duration"),
        ("table_row", "Sensory | Under one second"),
    ]
    assert document.blocks[1].emphasis == ["Encoding"]


def test_pptx_titles_bullets_levels_and_notes(tmp_path):
    data = make_pptx([
        ("Learning Theories", [("Behaviorism", 0), ("Classical conditioning", 1)], "Pavlov studied dogs."),
        ("Cognitivism", [("Information processing", 0)], ""),
    ])
    document = parse_file(write(tmp_path, "deck.pptx", data), "pptx")
    blocks = [(b.kind, b.text, b.level, b.page) for b in document.blocks]
    assert blocks[:5] == [
        ("heading", "Learning Theories", 2, 1),
        ("list_item", "Behaviorism", 0, 1),
        ("list_item", "Classical conditioning", 1, 1),
        ("paragraph", "Source: class handout", 0, 1),
        ("note", "Pavlov studied dogs.", 0, 1),
    ]
    assert document.page_label == "slide" and document.page_count == 2
    assert "[slide 2]" in to_markup(document)


def test_sandboxed_extraction_returns_document(tmp_path):
    path = write(tmp_path, "lesson.txt", LESSON.encode())
    document = extract_document(path, "txt")
    assert document.blocks[0].text == "CELL BIOLOGY"


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("broken.pdf", b"%PDF-1.4\n%garbage that is not a pdf", "unreadable"),
        ("broken.docx", b"PK\x03\x04 not really a zip", "unreadable"),
    ],
)
def test_malformed_files_are_rejected(tmp_path, name, data, code):
    with pytest.raises(IngestError) as caught:
        extract_document(write(tmp_path, name, data), name.rsplit(".", 1)[1])
    assert caught.value.code == code


def test_docx_with_entity_expansion_is_rejected(tmp_path):
    hostile = rewrite_zip(make_docx(lambda doc: doc.add_paragraph("x")), replace={"word/document.xml": BILLION_LAUGHS})
    with pytest.raises(IngestError) as caught:
        parse_file(write(tmp_path, "hostile.docx", hostile), "docx")
    assert caught.value.code == "unsafe_document"


def test_zip_bomb_is_rejected(tmp_path):
    bomb = rewrite_zip(make_docx(lambda doc: doc.add_paragraph("x")), extra={"word/media/padding.bin": b"\0" * (20 * 1024 * 1024)})
    with pytest.raises(IngestError) as caught:
        parse_file(write(tmp_path, "bomb.docx", bomb), "docx")
    assert caught.value.code == "too_large"


def test_too_many_zip_entries_is_rejected(tmp_path):
    many = rewrite_zip(make_docx(lambda doc: doc.add_paragraph("x")), extra={f"junk/{i}.bin": b"x" for i in range(3100)})
    with pytest.raises(IngestError) as caught:
        parse_file(write(tmp_path, "many.docx", many), "docx")
    assert caught.value.code == "too_complex"


def _sleepy_child(connection, seconds: float) -> None:  # noqa: ANN001
    time.sleep(seconds)
    connection.send(("ok", {}))


def test_isolated_parse_times_out():
    started = time.monotonic()
    with pytest.raises(IngestError) as caught:
        run_isolated(_sleepy_child, (30,), timeout=1.5)
    assert caught.value.code == "timeout"
    assert time.monotonic() - started < 10


def test_truncation_limits_extracted_text():
    document = Document("txt", [Block("paragraph", "x" * 600) for _ in range(5)])
    truncate(document, limit=1500)
    assert len(document.blocks) == 2 and "truncated" in document.warnings


SYLLABUS = """ARELLANO UNIVERSITY
College of Arts and Sciences

COURSE SYLLABUS

Course Code: PSYCH 101
Course Title: Introduction to Psychology
Credit Units: 3

Course Outline

Week 1: Course Orientation
Week 2: History and Approaches of Psychology (3 hrs)
Week 3: Biological Bases of Behavior
Week 4-5: Sensation and Perception
Week 6: Prelim Examination
Week 7: Learning and Conditioning
Week 8: Memory

Grading System
Quizzes 30%
"""


def test_syllabus_text_proposal():
    proposal = propose_topics(parse_text(SYLLABUS))
    assert proposal.name == "Introduction to Psychology"
    assert proposal.code == "PSYCH 101"
    assert proposal.topics == [
        "History and Approaches of Psychology",
        "Biological Bases of Behavior",
        "Sensation and Perception",
        "Learning and Conditioning",
        "Memory",
    ]
    assert proposal.warnings == []


def test_syllabus_table_proposal(tmp_path):
    def build(doc):
        doc.add_paragraph("Republic of the Philippines")
        info = doc.add_table(rows=1, cols=2)
        info.cell(0, 0).text, info.cell(0, 1).text = "Descriptive Title", "Readings in Philippine History"
        doc.add_heading("Learning Plan", level=1)
        plan = doc.add_table(rows=5, cols=3)
        rows = [("Week", "Topics", "Assessment"), ("1", "Meaning and relevance of history", "Quiz"),
                ("2-3", "Content and contextual analysis of primary sources", "Essay"),
                ("4", "Midterm Examination", ""), ("5", "Social, political and economic issues", "Debate")]
        for row_cells, values in zip(plan.rows, rows):
            for cell, value in zip(row_cells.cells, values):
                cell.text = value

    proposal = propose_topics(parse_file(write(tmp_path, "syllabus.docx", make_docx(build)), "docx"))
    assert proposal.name == "Readings in Philippine History"
    assert proposal.topics == [
        "Meaning and relevance of history",
        "Content and contextual analysis of primary sources",
        "Social, political and economic issues",
    ]


def test_clean_topic_strips_dates_and_durations():
    assert clean_topic("Aug 12-16 Week 2: Cell Theory (3 hours)") == "Cell Theory"
    assert clean_topic("1. Introduction to Statistics;") == "Introduction to Statistics"


def test_routing_matches_sections_to_topics():
    sections = outline(parse_text(LESSON))
    topics = [(10, "Cell structure and function"), (11, "Photosynthesis and respiration"), (12, "Genetics")]
    routes = route_sections(sections, topics)
    assert [route.topic_id for route in routes[1:]] == [10, 11]
    assert route_sections(sections, topics, fixed_topic=12)[0].topic_id == 12
    assert route_sections(outline(parse_text("# Unrelated\n\nBasketball drills.")), topics)[0].topic_id is None


def test_language_detection():
    english = "The cell is the basic unit of life and it is made of many parts that work together in the body. " * 3
    filipino = "Ang selula ay ang pinakamaliit na yunit ng buhay at ito ay may mga bahagi na nagtutulungan sa katawan. " * 3
    assert detect_language(english) == "en"
    assert detect_language(filipino) == "tl"
    assert detect_language("too short") == "unknown"
