import random
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import now_local
from app.core.errors import ApiError, conflict
from app.ml import bkt
from app.ml.qlearning import (
    ACTIVITY_MINUTES,
    ACTIVITY_QUESTIONS,
    QLearner,
    compute_reward,
    eligible_actions,
    make_state,
    urgency_bucket,
)
from app.models import (
    Enrollment,
    Material,
    QCell,
    Recommendation,
    Requirement,
    StudySession,
    Subject,
    Topic,
    TopicMastery,
    User,
)
from app.schemas import AnswerIn
from app.scheduling.planner import MIN_SLOT_MINUTES, available_minutes
from app.services import assessment, content, notify, schedule

URGENCY_WEIGHT = {0: 0.0, 1: 0.3, 2: 0.6}
OPEN_STATUSES = ("pending", "started")
MASTERY_LABEL = {"0": "low", "1": "developing", "2": "fairly strong", "3": "strong"}
URGENCY_LABEL = {"0": "", "1": " A related deadline is within a week.", "2": " A related deadline is very close."}


@dataclass
class Candidate:
    topic: Topic
    mastery: TopicMastery
    days_to_due: float | None
    score: float


def load_learner(db: Session) -> QLearner:
    rows = {(c.state, c.action): (c.q_value, c.visits) for c in db.scalars(select(QCell)).all()}
    return QLearner.from_rows(rows)


def _locked_cell(db: Session, state: str, action: str) -> QCell | None:
    return db.scalar(
        select(QCell)
        .where(QCell.state == state, QCell.action == action)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _update_q(
    db: Session, state: str, action: str, reward: float, next_state: str, next_eligible: list[str]
) -> float:
    """Q-update under a row lock so concurrent completions never overwrite each other's update."""
    for _attempt in range(2):
        learner = load_learner(db)
        cell = _locked_cell(db, state, action)
        if cell is not None:
            learner.q[(state, action)], learner.visits[(state, action)] = cell.q_value, cell.visits
        new_q = learner.update(state, action, reward, next_state, next_eligible)
        visits = learner.visits[(state, action)]
        if cell is not None:
            cell.q_value, cell.visits = new_q, visits
            return new_q
        try:
            with db.begin_nested():
                db.add(QCell(state=state, action=action, q_value=new_q, visits=visits))
            return new_q
        except IntegrityError:
            continue
    raise RuntimeError("Could not save the Q-table update.")


def _days_to_due(db: Session, user_id: int, topic: Topic, now: datetime) -> float | None:
    due_dates = db.scalars(
        select(Requirement.due_at).where(
            Requirement.user_id == user_id,
            Requirement.done.is_(False),
            (Requirement.topic_id == topic.id)
            | ((Requirement.topic_id.is_(None)) & (Requirement.subject_id == topic.subject_id)),
        )
    ).all()
    if not due_dates:
        return None
    return max(0.0, (min(due_dates) - now).total_seconds() / 86400.0)


def _hours_since(mastery: TopicMastery, now: datetime) -> float | None:
    if mastery.last_activity_at is None:
        return None
    return max(0.0, (now - mastery.last_activity_at).total_seconds() / 3600.0)


def _material_count(db: Session, user: User, topic: Topic) -> int:
    return len(db.scalars(content.material_query(user, topic)).all())


def _candidates(db: Session, user: User, now: datetime) -> tuple[list[Candidate], str]:
    topics = db.scalars(
        select(Topic)
        .join(Subject, Topic.subject_id == Subject.id)
        .join(Enrollment, (Enrollment.subject_id == Subject.id) & (Enrollment.user_id == user.id))
        .where(content.visible_subject_filter(user))
        .order_by(Topic.id)
    ).all()
    if not topics:
        return [], "no_topics"
    candidates: list[Candidate] = []
    blocked = {"not_ready": 0, "diagnostic": 0, "mastered": 0}
    for topic in topics:
        if not content.topic_ready(db, user, topic):
            blocked["not_ready"] += 1
            continue
        mastery = content.get_mastery(db, user, topic)
        if not mastery.diagnostic_done:
            blocked["diagnostic"] += 1
            continue
        if bkt.is_mastered(mastery.p_mastery):
            blocked["mastered"] += 1
            continue
        days = _days_to_due(db, user.id, topic, now)
        score = (1.0 - mastery.p_mastery) + URGENCY_WEIGHT[urgency_bucket(days)]
        candidates.append(Candidate(topic, mastery, days, score))
    if candidates:
        return sorted(candidates, key=lambda c: (-c.score, c.topic.id)), ""
    reason = max(blocked, key=lambda k: blocked[k])
    return [], {"not_ready": "not_ready", "diagnostic": "diagnostic_needed", "mastered": "all_mastered"}[reason]


_EMPTY_MESSAGES = {
    "no_topics": "Enroll in a subject with topics first.",
    "not_ready": f"Your topics need at least {content.MIN_QUESTIONS} questions each. Add questions to a topic.",
    "diagnostic_needed": "Take the starting quiz for a topic first. It sets your baseline.",
    "all_mastered": "You have mastered every topic you are enrolled in. Add a new topic or subject.",
}


def current_open(db: Session, user: User) -> Recommendation | None:
    return db.scalar(
        select(Recommendation)
        .where(Recommendation.user_id == user.id, Recommendation.status.in_(OPEN_STATUSES))
        .order_by(Recommendation.id.desc())
    )


def next_recommendation(
    db: Session, user: User, rng: random.Random | None = None, now: datetime | None = None
) -> Recommendation:
    now = now or now_local()
    rng = rng or random.Random()
    open_recommendation = current_open(db, user)
    if open_recommendation:
        return open_recommendation

    slots = schedule.upcoming_free_slots(db, user, now)
    free_minutes = available_minutes(slots, now)
    if free_minutes < MIN_SLOT_MINUTES:
        notify.create(
            db,
            user.id,
            f"noslot:{now:%Y-%m-%d}",
            "schedule_change",
            "No free study time found",
            "There is no free slot of at least 15 minutes in the next 7 days. "
            "Adjust your study hours or commitments to get a recommendation.",
            "/plan",
        )
        db.commit()
        raise conflict("no_free_time", "No free time of at least 15 minutes in the next 7 days. Adjust your study hours or schedule.")

    candidates, empty_reason = _candidates(db, user, now)
    if not candidates:
        db.commit()
        raise conflict(empty_reason, _EMPTY_MESSAGES[empty_reason])

    learner = load_learner(db)
    for candidate in candidates:
        topic = candidate.topic
        eligible = eligible_actions(
            free_minutes, _material_count(db, user, topic) > 0, content.question_count(db, user, topic.id)
        )
        if not eligible:
            continue
        state = make_state(candidate.mastery.p_mastery, candidate.days_to_due, free_minutes, _hours_since(candidate.mastery, now))
        action, explored = learner.select(state, eligible, rng)
        recommendation = Recommendation(
            user_id=user.id,
            topic_id=topic.id,
            activity_type=action,
            state_key=state,
            q_value=learner.value(state, action),
            explored=explored,
            epsilon=learner.epsilon,
            available_minutes=free_minutes,
            created_at=now,
        )
        db.add(recommendation)
        db.flush()
        session = schedule.place_session(db, user, recommendation, now)
        _notify_created(db, user, recommendation, topic, session)
        db.commit()
        return recommendation

    db.commit()
    raise conflict(
        "no_eligible_activity",
        f"Your next free slot is only {int(free_minutes)} minutes. Add materials to a topic or free up more time.",
    )


def _notify_created(db: Session, user: User, recommendation: Recommendation, topic: Topic, session: StudySession) -> None:
    label = recommendation.activity_type.replace("_", " ")
    if session.start_at is None:
        notify.create(
            db, user.id, f"unplaced-rec:{recommendation.id}", "schedule_change",
            "Recommendation could not be scheduled",
            f"{label.title()} for {topic.name} found no free slot under your current commitments.", "/plan",
        )
        return
    notify.create(
        db, user.id, f"rec:{recommendation.id}", "recommendation", "New recommended activity",
        f"{label.title()}: {topic.name}, planned for {session.start_at:%a %b %d at %I:%M %p}.",
        f"/activity/{recommendation.id}",
    )


def get_recommendation(db: Session, user: User, recommendation_id: int) -> Recommendation:
    recommendation = db.scalar(
        select(Recommendation).where(Recommendation.id == recommendation_id, Recommendation.user_id == user.id)
    )
    if recommendation is None:
        raise ApiError(404, "not_found", "Recommendation not found.")
    return recommendation


def reason_text(recommendation: Recommendation) -> str:
    mastery_digit, urgency_digit = recommendation.state_key[1], recommendation.state_key[4]
    text = f"Your mastery of this topic is {MASTERY_LABEL[mastery_digit]}.{URGENCY_LABEL[urgency_digit]}"
    if recommendation.explored:
        text += " This activity was chosen as an exploration step to learn what works."
    return text


def start_activity(db: Session, user: User, recommendation: Recommendation) -> tuple[list[Material], list]:
    if recommendation.status not in OPEN_STATUSES:
        raise conflict("already_finished", "This activity is already finished.")
    topic = db.get(Topic, recommendation.topic_id)
    mastery = content.get_mastery(db, user, topic)
    if recommendation.status == "pending":
        recommendation.status = "started"
        recommendation.mastery_before = mastery.p_mastery
    activity = recommendation.activity_type
    materials: list[Material] = []
    questions: list = []
    if activity in ("review_material", "revisit"):
        materials = list(db.scalars(content.material_query(user, topic).order_by(Material.created_at.desc())).all())
    count = ACTIVITY_QUESTIONS[activity]
    if count:
        questions = assessment.practice_questions(db, user, topic, count)
    db.commit()
    return materials, questions


def _finish(
    db: Session, user: User, recommendation: Recommendation, before: float, after: float, skipped: bool, now: datetime
) -> float:
    topic = db.get(Topic, recommendation.topic_id)
    mastery = content.get_mastery(db, user, topic)
    reward = compute_reward(before, after, skipped)
    days = _days_to_due(db, user.id, topic, now)
    next_state = make_state(after, days, recommendation.available_minutes, 0.0)
    next_eligible = eligible_actions(
        recommendation.available_minutes, _material_count(db, user, topic) > 0, content.question_count(db, user, topic.id)
    )
    new_q = _update_q(db, recommendation.state_key, recommendation.activity_type, reward, next_state, next_eligible)

    recommendation.status = "skipped" if skipped else "completed"
    recommendation.mastery_before, recommendation.mastery_after = before, after
    recommendation.reward, recommendation.next_state_key, recommendation.q_value_after = reward, next_state, new_q
    recommendation.completed_at = now
    if recommendation.session:
        recommendation.session.status = "skipped" if skipped else "completed"
    if not skipped:
        content.touch_activity(mastery)
    return reward


def complete_review(db: Session, user: User, recommendation: Recommendation) -> float:
    if recommendation.status not in OPEN_STATUSES:
        raise conflict("already_finished", "This activity is already finished.")
    if ACTIVITY_QUESTIONS[recommendation.activity_type]:
        raise conflict("answers_required", "This activity is completed by answering its questions.")
    topic = db.get(Topic, recommendation.topic_id)
    mastery = content.get_mastery(db, user, topic)
    reward = _finish(db, user, recommendation, mastery.p_mastery, mastery.p_mastery, False, now_local())
    db.commit()
    return reward


def complete_with_answers(
    db: Session, user: User, recommendation: Recommendation, answers: list[AnswerIn]
) -> tuple[assessment.SubmitResult, float]:
    if recommendation.status not in OPEN_STATUSES:
        raise conflict("already_finished", "This activity is already finished.")
    if not ACTIVITY_QUESTIONS[recommendation.activity_type]:
        raise conflict("no_questions", "This activity has no questions to answer.")
    topic = db.get(Topic, recommendation.topic_id)
    result = assessment.submit_answers(db, user, topic, recommendation.activity_type, answers, recommendation.id)
    before = recommendation.mastery_before if recommendation.mastery_before is not None else result.mastery_before
    reward = _finish(db, user, recommendation, before, result.mastery_after, False, now_local())
    db.commit()
    return result, reward


def skip(db: Session, user: User, recommendation: Recommendation) -> float:
    if recommendation.status not in OPEN_STATUSES:
        raise conflict("already_finished", "This activity is already finished.")
    topic = db.get(Topic, recommendation.topic_id)
    mastery = content.get_mastery(db, user, topic)
    reward = _finish(db, user, recommendation, mastery.p_mastery, mastery.p_mastery, True, now_local())
    db.commit()
    return reward


def duration_minutes(recommendation: Recommendation) -> int:
    return ACTIVITY_MINUTES[recommendation.activity_type]
