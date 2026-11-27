from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ApiError, bad_request, not_found
from app.models import Question
from app.schemas import BulkResult, QuestionBulkIn, QuestionIn, QuestionOwnOut
from app.services import content
from app.services.question_import import parse_bulk_text, parse_csv

router = APIRouter(tags=["questions"])

MAX_CSV_BYTES = 512 * 1024


def _save(db: DbSession, user_id: int, topic_id: int, items: list[QuestionIn]) -> int:
    existing = {
        q.lower()
        for q in db.scalars(
            select(Question.text).where(Question.topic_id == topic_id, Question.owner_id == user_id)
        ).all()
    }
    created = 0
    for item in items:
        if item.text.lower() in existing:
            continue
        existing.add(item.text.lower())
        db.add(
            Question(
                topic_id=topic_id,
                owner_id=user_id,
                text=item.text,
                choices=item.choices,
                correct_index=item.correct_index,
                explanation=item.explanation,
            )
        )
        created += 1
    db.commit()
    return created


@router.get("/topics/{topic_id}/my-questions", response_model=list[QuestionOwnOut])
def my_questions(topic_id: int, user: CurrentUser, db: DbSession) -> list[Question]:
    topic = content.get_visible_topic(db, user, topic_id)
    return list(
        db.scalars(
            select(Question).where(Question.topic_id == topic.id, Question.owner_id == user.id).order_by(Question.id)
        ).all()
    )


@router.post("/topics/{topic_id}/questions", response_model=BulkResult, status_code=201)
def add_question(topic_id: int, payload: QuestionIn, user: CurrentUser, db: DbSession) -> BulkResult:
    topic = content.get_visible_topic(db, user, topic_id)
    created = _save(db, user.id, topic.id, [payload])
    return BulkResult(created=created, errors=[] if created else ["You already added this question."])


@router.post("/topics/{topic_id}/questions/bulk", response_model=BulkResult, status_code=201)
def add_questions_bulk(topic_id: int, payload: QuestionBulkIn, user: CurrentUser, db: DbSession) -> BulkResult:
    topic = content.get_visible_topic(db, user, topic_id)
    questions, errors = parse_bulk_text(payload.text)
    if errors and not questions:
        raise ApiError(422, "no_valid_questions", "; ".join(errors[:5]))
    return BulkResult(created=_save(db, user.id, topic.id, questions), errors=errors)


@router.post("/topics/{topic_id}/questions/csv", response_model=BulkResult, status_code=201)
async def add_questions_csv(
    topic_id: int, user: CurrentUser, db: DbSession, file: Annotated[UploadFile, File()]
) -> BulkResult:
    topic = content.get_visible_topic(db, user, topic_id)
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise bad_request("file_too_large", "CSV files must be 512 KB or smaller.")
    questions, errors = parse_csv(raw)
    if errors and not questions:
        raise ApiError(422, "no_valid_questions", "; ".join(errors[:5]))
    return BulkResult(created=_save(db, user.id, topic.id, questions), errors=errors)


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: int, user: CurrentUser, db: DbSession) -> None:
    question = db.scalar(select(Question).where(Question.id == question_id, Question.owner_id == user.id))
    if question is None:
        raise not_found("Question")
    db.delete(question)
    db.commit()
