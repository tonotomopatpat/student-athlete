import random
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, bad_request, conflict
from app.ml import bkt
from app.models import Question, Response, Topic, User
from app.schemas import AnswerIn
from app.services import content

DIAGNOSTIC_SIZE = 5
MAX_FLAGGED_DIAGNOSTIC = 6


@dataclass
class GradedAnswer:
    question: Question
    correct: bool
    mastery_after: float


@dataclass
class SubmitResult:
    mastery_before: float
    mastery_after: float
    graded: list[GradedAnswer]


def _visible_questions(db: Session, user: User, topic_id: int) -> list[Question]:
    return list(
        db.scalars(
            select(Question).where(Question.topic_id == topic_id, content.visible_question_filter(user))
        ).all()
    )


def diagnostic_questions(db: Session, user: User, topic: Topic, rng: random.Random | None = None) -> list[Question]:
    rng = rng or random.Random()
    questions = _visible_questions(db, user, topic.id)
    flagged = [q for q in questions if q.is_diagnostic]
    if flagged:
        return flagged[:MAX_FLAGGED_DIAGNOSTIC]
    return rng.sample(questions, min(DIAGNOSTIC_SIZE, len(questions)))


def practice_questions(
    db: Session, user: User, topic: Topic, limit: int, rng: random.Random | None = None
) -> list[Question]:
    """Prefer questions the student has answered least, random among ties."""
    rng = rng or random.Random()
    questions = _visible_questions(db, user, topic.id)
    counts = dict(
        db.execute(
            select(Response.question_id, func.count(Response.id))
            .where(Response.user_id == user.id, Response.topic_id == topic.id)
            .group_by(Response.question_id)
        ).all()
    )
    rng.shuffle(questions)
    questions.sort(key=lambda q: counts.get(q.id, 0))
    return questions[:limit]


def submit_answers(
    db: Session,
    user: User,
    topic: Topic,
    context: str,
    answers: Sequence[AnswerIn],
    recommendation_id: int | None = None,
) -> SubmitResult:
    """Grade answers in order, applying one BKT update per answer."""
    if len({a.question_id for a in answers}) != len(answers):
        raise bad_request("duplicate_answers", "Each question can only be answered once per submission.")
    questions = {q.id: q for q in _visible_questions(db, user, topic.id)}
    mastery = content.get_mastery(db, user, topic)
    if context == "diagnostic" and mastery.diagnostic_done:
        raise conflict("diagnostic_done", "The starting quiz for this topic is already completed.")

    params = content.topic_params(topic)
    before = mastery.p_mastery
    p = before
    graded: list[GradedAnswer] = []
    for answer in answers:
        question = questions.get(answer.question_id)
        if question is None:
            raise ApiError(400, "invalid_question", "One of the questions does not belong to this topic.")
        if answer.chosen_index >= len(question.choices):
            raise bad_request("invalid_choice", "Selected choice does not exist.")
        correct = answer.chosen_index == question.correct_index
        p_before = p
        p = bkt.update(p, correct, params)
        db.add(
            Response(
                user_id=user.id,
                question_id=question.id,
                topic_id=topic.id,
                recommendation_id=recommendation_id,
                context=context,
                chosen_index=answer.chosen_index,
                correct=correct,
                mastery_before=p_before,
                mastery_after=p,
            )
        )
        graded.append(GradedAnswer(question, correct, p))

    mastery.p_mastery = p
    mastery.response_count += len(graded)
    if context == "diagnostic":
        mastery.diagnostic_done = True
    content.touch_activity(mastery)
    return SubmitResult(mastery_before=before, mastery_after=p, graded=graded)
