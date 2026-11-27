"""Gold lessons and syllabi: the real-world test data the generator is measured on.

Files live in data/gold/files/ (git-ignored unless openly licensed); data/gold/manifest.csv describes each one.
Held-out (test) assignments are frozen: once a row has a split it is never changed by `gold-split`.
"""

import csv
import hashlib
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import BACKEND_DIR

GOLD_DIR = BACKEND_DIR / "data" / "gold"
MANIFEST_PATH = GOLD_DIR / "manifest.csv"
FILES_DIR = GOLD_DIR / "files"

COLUMNS = (
    "doc_id", "kind", "subject", "format", "material_type", "path",
    "source", "license", "language", "sha256", "split", "notes",
)
KINDS = ("lesson", "syllabus")
FORMATS = ("pdf", "docx", "pptx", "txt")
MATERIAL_TYPES = ("slides", "handout", "textbook", "notes", "syllabus")
SPLITS = ("dev", "test")
TEST_SHARE = 0.4
SPLIT_SEED = 20260302

MIN_LESSONS = 20
MIN_SUBJECTS = 4
MIN_SYLLABI = 15


@dataclass
class ManifestReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, Counter] = field(default_factory=dict)


def read_manifest(path: Path = MANIFEST_PATH) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"manifest is missing columns: {', '.join(missing)}")
        return [{column: (row.get(column) or "").strip() for column in COLUMNS} for row in reader]


def write_manifest(rows: list[dict[str, str]], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_row(index: int, row: dict[str, str], files_dir: Path, errors: list[str]) -> None:
    where = f"row {index} ({row['doc_id'] or 'no doc_id'})"
    for column, allowed in (("kind", KINDS), ("format", FORMATS), ("material_type", MATERIAL_TYPES)):
        if row[column] not in allowed:
            errors.append(f"{where}: {column} must be one of {', '.join(allowed)}")
    if row["split"] and row["split"] not in SPLITS:
        errors.append(f"{where}: split must be empty, dev or test")
    for column in ("doc_id", "subject", "path", "source", "license", "language"):
        if not row[column]:
            errors.append(f"{where}: {column} is required")
    if (row["kind"] == "syllabus") != (row["material_type"] == "syllabus"):
        errors.append(f"{where}: kind 'syllabus' and material_type 'syllabus' go together")
    if not row["path"]:
        return
    file_path = (files_dir / row["path"]).resolve()
    if not file_path.is_relative_to(files_dir.resolve()):
        errors.append(f"{where}: path must stay inside {files_dir}")
        return
    if not file_path.is_file():
        errors.append(f"{where}: file not found: {row['path']}")
        return
    if file_path.suffix.lower().lstrip(".") != row["format"]:
        errors.append(f"{where}: file extension does not match format '{row['format']}'")
    if row["sha256"] and row["sha256"] != file_sha256(file_path):
        errors.append(f"{where}: file changed after it was registered (sha256 mismatch)")


def validate(rows: list[dict[str, str]], files_dir: Path = FILES_DIR) -> ManifestReport:
    report = ManifestReport()
    for index, row in enumerate(rows, start=2):
        _check_row(index, row, files_dir, report.errors)
    for column in ("doc_id", "sha256"):
        repeated = [value for value, count in Counter(r[column] for r in rows if r[column]).items() if count > 1]
        for value in repeated:
            report.errors.append(f"duplicate {column}: {value}")

    lessons = [row for row in rows if row["kind"] == "lesson"]
    syllabi = [row for row in rows if row["kind"] == "syllabus"]
    subjects = {row["subject"].lower() for row in lessons}
    if len(lessons) < MIN_LESSONS:
        report.warnings.append(f"{len(lessons)} lessons; the plan needs at least {MIN_LESSONS}")
    if len(subjects) < MIN_SUBJECTS:
        report.warnings.append(f"{len(subjects)} lesson subjects; the plan needs at least {MIN_SUBJECTS}")
    if len(syllabi) < MIN_SYLLABI:
        report.warnings.append(f"{len(syllabi)} syllabi; the plan needs at least {MIN_SYLLABI}")
    unsplit = sum(1 for row in rows if not row["split"])
    if unsplit:
        report.warnings.append(f"{unsplit} documents have no split yet; run gold-split")

    report.counts = {
        "kind": Counter(row["kind"] for row in rows),
        "split": Counter(row["split"] or "unassigned" for row in rows),
        "subject": Counter(row["subject"] for row in lessons),
        "material_type": Counter(row["material_type"] for row in lessons),
    }
    return report


def assign_splits(rows: list[dict[str, str]], seed: int = SPLIT_SEED) -> list[dict[str, str]]:
    """Fill empty splits, stratified by kind and subject, keeping every existing assignment."""
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["kind"], row["subject"].lower())].append(row)
    rng = random.Random(seed)
    for key in sorted(groups):
        group = groups[key]
        open_rows = sorted((row for row in group if not row["split"]), key=lambda row: row["doc_id"])
        rng.shuffle(open_rows)
        wanted_test = round(len(group) * TEST_SHARE)
        have_test = sum(1 for row in group if row["split"] == "test")
        for row in open_rows:
            if have_test < wanted_test:
                row["split"] = "test"
                have_test += 1
            else:
                row["split"] = "dev"
    return rows


def fill_hashes(rows: list[dict[str, str]], files_dir: Path = FILES_DIR) -> list[dict[str, str]]:
    for row in rows:
        file_path = files_dir / row["path"]
        if not row["sha256"] and row["path"] and file_path.is_file():
            row["sha256"] = file_sha256(file_path)
    return rows
