from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import conflict
from app.ml.bkt import is_mastered
from app.schemas import AnswerResult, QuestionPublic, SubmitIn, SubmitOut
from app.services import assessment, content

router = APIRouter(tags=["assessments"])


def _require_enrolled_and_ready(db: DbSession, user, topic) -> None:
    if not content.is_enrolled(db, user, topic.subject_id):
        raise conflict("not_enrolled", "Enroll in this subject first.")
    if not content.topic_ready(db, user, topic):
        raise conflict(
            "not_enough_questions",
            f"This topic needs at least {content.MIN_QUESTIONS} questions before it can be assessed.",
        )


def result_payload(topic_id: int, result: assessment.SubmitResult) -> SubmitOut:
    graded = result.graded
    return SubmitOut(
        topic_id=topic_id,
        mastery_before=result.mastery_before,
        mastery_after=result.mastery_after,
        correct_count=sum(1 for g in graded if g.correct),
        total=len(graded),
        results=[
            AnswerResult(
                question_id=g.question.id,
                correct=g.correct,
                correct_index=g.question.correct_index,
                explanation=g.question.explanation,
                mastery_after=g.mastery_after,
            )
            for g in graded
        ],
        mastered=is_mastered(result.mastery_after),
    )


@router.get("/topics/{topic_id}/questions", response_model=list[QuestionPublic])
def topic_questions(
    topic_id: int,
    user: CurrentUser,
    db: DbSession,
    mode: Literal["diagnostic", "practice"] = "practice",
    limit: int = Query(default=5, ge=1, le=20),
) -> list[QuestionPublic]:
    topic = content.get_visible_topic(db, user, topic_id)
    _require_enrolled_and_ready(db, user, topic)
    if mode == "diagnostic":
        mastery = content.get_mastery(db, user, topic)
        if mastery.diagnostic_done:
            raise conflict("diagnostic_done", "The starting quiz for this topic is already completed.")
        questions = assessment.diagnostic_questions(db, user, topic)
    else:
        questions = assessment.practice_questions(db, user, topic, limit)
    db.commit()
    return [QuestionPublic(id=q.id, text=q.text, choices=q.choices) for q in questions]


@router.post("/assessments/submit", response_model=SubmitOut)
def submit_assessment(payload: SubmitIn, user: CurrentUser, db: DbSession) -> SubmitOut:
    topic = content.get_visible_topic(db, user, payload.topic_id)
    _require_enrolled_and_ready(db, user, topic)
    result = assessment.submit_answers(db, user, topic, payload.context, payload.answers)
    db.commit()
    return result_payload(topic.id, result)
