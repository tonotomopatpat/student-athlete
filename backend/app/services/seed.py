import csv
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Question, Subject, Topic
from app.sample_data import SAMPLE_SUBJECTS
from app.schemas import QuestionIn
from app.services.question_import import question_from_row

DIAGNOSTIC_PER_TOPIC = 3


@dataclass
class ImportReport:
    subjects: int = 0
    topics: int = 0
    questions: int = 0
    skipped_duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def _get_subject(db: Session, code: str, name: str, description: str, is_sample: bool, report: ImportReport) -> Subject:
    subject = db.scalar(select(Subject).where(Subject.code == code))
    if subject is None:
        subject = Subject(code=code, name=name, description=description, owner_id=None, is_sample=is_sample)
        db.add(subject)
        db.flush()
        report.subjects += 1
    return subject


def _get_topic(db: Session, subject: Subject, name: str, report: ImportReport) -> Topic:
    topic = db.scalar(select(Topic).where(Topic.subject_id == subject.id, Topic.name == name))
    if topic is None:
        position = len(db.scalars(select(Topic.id).where(Topic.subject_id == subject.id)).all()) + 1
        topic = Topic(subject_id=subject.id, name=name, position=position)
        db.add(topic)
        db.flush()
        report.topics += 1
    return topic


def _add_question(db: Session, topic: Topic, item: QuestionIn, diagnostic: bool, report: ImportReport) -> None:
    duplicate = db.scalar(
        select(Question.id).where(Question.topic_id == topic.id, Question.owner_id.is_(None), Question.text == item.text)
    )
    if duplicate:
        report.skipped_duplicates += 1
        return
    db.add(
        Question(
            topic_id=topic.id,
            owner_id=None,
            text=item.text,
            choices=item.choices,
            correct_index=item.correct_index,
            explanation=item.explanation,
            is_diagnostic=diagnostic,
        )
    )
    report.questions += 1


def seed_samples(db: Session) -> ImportReport:
    report = ImportReport()
    for definition in SAMPLE_SUBJECTS:
        subject = _get_subject(db, definition["code"], definition["name"], definition["description"], True, report)
        for topic_def in definition["topics"]:
            topic = _get_topic(db, subject, topic_def["name"], report)
            for index, (text, choices, correct, explanation) in enumerate(topic_def["questions"]):
                item = QuestionIn(text=text, choices=choices, correct_index=correct, explanation=explanation)
                _add_question(db, topic, item, index < DIAGNOSTIC_PER_TOPIC, report)
    db.commit()
    return report


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "yes", "y", "true", "x"}


def import_questions_csv(db: Session, path: Path) -> ImportReport:
    """Load the built-in question bank. Required columns: subject_code, subject_name, topic, question,
    choice_a, choice_b, ..., correct. Optional: explanation, diagnostic, description."""
    report = ImportReport()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        _import_rows(db, reader, report)
    if report.errors:
        db.rollback()
        report.subjects = report.topics = report.questions = 0
        return report
    db.commit()
    return report


def _import_rows(db: Session, rows: Iterable[dict[str, str]], report: ImportReport) -> None:
    for number, row in enumerate(rows, start=2):
        normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        code, name, topic_name = normalized.get("subject_code"), normalized.get("subject_name"), normalized.get("topic")
        if not code or not name or not topic_name:
            report.errors.append(f"Row {number}: subject_code, subject_name and topic are required.")
            continue
        try:
            item = question_from_row(normalized)
        except (ValidationError, ValueError) as error:
            report.errors.append(f"Row {number}: {error}")
            continue
        subject = _get_subject(db, code, name, normalized.get("description", ""), False, report)
        topic = _get_topic(db, subject, topic_name, report)
        _add_question(db, topic, item, _truthy(normalized.get("diagnostic")), report)
