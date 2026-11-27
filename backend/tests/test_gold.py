from collections import Counter

from app.evaluation import gold, outline


def make_row(doc_id: str, subject: str = "Biology", kind: str = "lesson", split: str = "", **overrides) -> dict:
    row = {column: "" for column in gold.COLUMNS}
    row.update(
        doc_id=doc_id, kind=kind, subject=subject, format="txt",
        material_type="syllabus" if kind == "syllabus" else "handout",
        path=f"{doc_id}.txt", source="https://openstax.org", license="CC BY 4.0", language="en", split=split,
    )
    row.update(overrides)
    return row


def write_files(tmp_path, rows):
    for row in rows:
        (tmp_path / row["path"]).write_text(f"content of {row['doc_id']}")


def test_manifest_round_trip_and_valid_rows(tmp_path):
    rows = [make_row("bio-01"), make_row("psy-01", subject="Psychology")]
    write_files(tmp_path, rows)
    gold.write_manifest(rows, tmp_path / "manifest.csv")
    loaded = gold.read_manifest(tmp_path / "manifest.csv")
    assert loaded == rows
    assert gold.validate(gold.fill_hashes(loaded, tmp_path), tmp_path).errors == []


def test_validation_reports_each_problem(tmp_path):
    rows = [
        make_row("a", format="doc"),
        make_row("b", license=""),
        make_row("c", path="../outside.txt"),
        make_row("d", path="missing.txt"),
        make_row("a"),
        make_row("e", kind="syllabus", material_type="slides"),
    ]
    write_files(tmp_path, [rows[0], rows[1], rows[4], rows[5]])
    errors = "\n".join(gold.validate(rows, tmp_path).errors)
    assert "format must be one of" in errors
    assert "license is required" in errors
    assert "path must stay inside" in errors
    assert "file not found: missing.txt" in errors
    assert "duplicate doc_id: a" in errors
    assert "go together" in errors


def test_changed_file_is_detected(tmp_path):
    rows = [make_row("bio-01")]
    write_files(tmp_path, rows)
    gold.fill_hashes(rows, tmp_path)
    (tmp_path / "bio-01.txt").write_text("edited after freezing")
    assert any("sha256 mismatch" in error for error in gold.validate(rows, tmp_path).errors)


def test_split_is_stratified_deterministic_and_keeps_frozen_rows():
    rows = [make_row(f"bio-{i:02}") for i in range(10)] + [make_row(f"psy-{i:02}", "Psychology") for i in range(5)]
    rows[0]["split"] = "dev"
    first = gold.assign_splits([dict(row) for row in rows])
    second = gold.assign_splits([dict(row) for row in rows])
    assert first == second
    assert first[0]["split"] == "dev"
    by_subject = Counter((row["subject"], row["split"]) for row in first)
    assert by_subject[("Biology", "test")] == 4
    assert by_subject[("Psychology", "test")] == 2

    added = first + [make_row("bio-10"), make_row("bio-11")]
    resplit = gold.assign_splits([dict(row) for row in added])
    assert [row["split"] for row in resplit[:15]] == [row["split"] for row in first]


def test_shortfall_warnings():
    report = gold.validate([], gold.FILES_DIR)
    assert len(report.warnings) == 3


def test_outline_matching_is_one_to_one():
    proposed = ["History of Psychology", "Memory", "Memory and forgetting", "Orientation"]
    expected = ["History and approaches of psychology", "Memory and forgetting", "Learning"]
    assert outline.match_count(proposed, expected) == 2
    assert outline.match_count([], expected) == 0
