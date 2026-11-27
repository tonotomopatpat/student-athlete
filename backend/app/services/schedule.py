from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_local
from app.ml.qlearning import ACTIVITY_MINUTES
from app.models import Commitment, Recommendation, StudySession, User
from app.scheduling.planner import (
    CommitmentRule,
    Interval,
    expand_commitment,
    find_slot,
    free_slots,
)
from app.services import notify

HORIZON_DAYS = 7


def commitment_occurrences(db: Session, user_id: int, start: datetime, end: datetime) -> list[tuple[Commitment, Interval]]:
    occurrences: list[tuple[Commitment, Interval]] = []
    for commitment in db.scalars(select(Commitment).where(Commitment.user_id == user_id)).all():
        rule = CommitmentRule(commitment.start_at, commitment.end_at, commitment.repeat_weekly, commitment.repeat_until)
        occurrences.extend((commitment, interval) for interval in expand_commitment(rule, start, end))
    return sorted(occurrences, key=lambda pair: pair[1].start)


def _other_session_intervals(db: Session, user_id: int, exclude_session_id: int | None) -> list[Interval]:
    sessions = db.scalars(
        select(StudySession).where(
            StudySession.user_id == user_id,
            StudySession.status == "scheduled",
            StudySession.start_at.is_not(None),
        )
    ).all()
    return [Interval(s.start_at, s.end_at) for s in sessions if s.id != exclude_session_id and s.end_at]


def user_free_slots(
    db: Session, user: User, start: datetime, end: datetime, exclude_session_id: int | None = None
) -> list[Interval]:
    busy = [interval for _, interval in commitment_occurrences(db, user.id, start, end)]
    busy.extend(_other_session_intervals(db, user.id, exclude_session_id))
    return free_slots(busy, start, end, user.study_window_start, user.study_window_end, user.buffer_minutes)


def upcoming_free_slots(db: Session, user: User, now: datetime | None = None) -> list[Interval]:
    now = now or now_local()
    return user_free_slots(db, user, now, now + timedelta(days=HORIZON_DAYS))


def place_session(db: Session, user: User, recommendation: Recommendation, now: datetime | None = None) -> StudySession:
    """Create a study session for the recommendation in the earliest feasible slot."""
    now = now or now_local()
    duration = ACTIVITY_MINUTES[recommendation.activity_type]
    slot = find_slot(upcoming_free_slots(db, user, now), duration, now)
    session = StudySession(
        user_id=user.id,
        recommendation_id=recommendation.id,
        start_at=slot.start if slot else None,
        end_at=slot.end if slot else None,
        status="scheduled" if slot else "needs_reschedule",
    )
    db.add(session)
    db.flush()
    return session


def _session_label(db: Session, session: StudySession) -> str:
    recommendation = db.get(Recommendation, session.recommendation_id)
    return recommendation.activity_type.replace("_", " ") if recommendation else "study session"


def _try_move(db: Session, user: User, session: StudySession, now: datetime) -> bool:
    duration = ACTIVITY_MINUTES[db.get(Recommendation, session.recommendation_id).activity_type]
    slots = user_free_slots(db, user, now, now + timedelta(days=HORIZON_DAYS), exclude_session_id=session.id)
    slot = find_slot(slots, duration, now)
    if slot is None:
        return False
    session.start_at, session.end_at, session.status = slot.start, slot.end, "scheduled"
    return True


def recheck_sessions(db: Session, user: User, now: datetime | None = None) -> None:
    """After a schedule change, move or flag sessions that no longer fit."""
    now = now or now_local()
    sessions = db.scalars(
        select(StudySession)
        .where(StudySession.user_id == user.id, StudySession.status == "scheduled", StudySession.start_at >= now)
        .order_by(StudySession.start_at)
    ).all()
    for session in sessions:
        slots = user_free_slots(db, user, now, now + timedelta(days=HORIZON_DAYS), exclude_session_id=session.id)
        if any(slot.start <= session.start_at and session.end_at <= slot.end for slot in slots):
            continue
        old_start = session.start_at
        label = _session_label(db, session)
        if _try_move(db, user, session, now):
            notify.create(
                db,
                user.id,
                f"moved:{session.id}:{session.start_at.isoformat()}",
                "schedule_change",
                "Study session moved",
                f"Your {label} session on {old_start:%a %b %d, %I:%M %p} conflicted with a schedule change. "
                f"It is now on {session.start_at:%a %b %d, %I:%M %p}.",
                "/today",
            )
        else:
            session.status, session.start_at, session.end_at = "needs_reschedule", None, None
            notify.create(
                db,
                user.id,
                f"unplaced:{session.id}:{old_start.isoformat()}",
                "schedule_change",
                "Could not reschedule a study session",
                f"Your {label} session on {old_start:%a %b %d, %I:%M %p} no longer fits and no free slot was "
                "found in the next 7 days. Adjust your schedule or study hours and re-plan.",
                "/plan",
            )


def replan_unscheduled(db: Session, user: User, now: datetime | None = None) -> int:
    """Try to place sessions that previously had no feasible slot. Returns how many were placed."""
    now = now or now_local()
    placed = 0
    sessions = db.scalars(
        select(StudySession).where(StudySession.user_id == user.id, StudySession.status == "needs_reschedule")
    ).all()
    for session in sessions:
        if _try_move(db, user, session, now):
            placed += 1
    return placed
