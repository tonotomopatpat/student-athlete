from datetime import datetime, time, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.clock import now_local
from app.core.errors import bad_request, not_found
from app.models import Commitment, Recommendation, Requirement, StudySession, Subject, Topic
from app.schemas import (
    CommitmentIn,
    CommitmentOut,
    OccurrenceOut,
    RequirementIn,
    RequirementOut,
    RequirementUpdate,
    ScheduleOut,
    SessionOut,
)
from app.services import content, schedule

router = APIRouter(tags=["schedule"])

MAX_RANGE_DAYS = 62


def _own_commitment(db: DbSession, user_id: int, commitment_id: int) -> Commitment:
    commitment = db.scalar(select(Commitment).where(Commitment.id == commitment_id, Commitment.user_id == user_id))
    if commitment is None:
        raise not_found("Commitment")
    return commitment


@router.get("/commitments", response_model=list[CommitmentOut])
def list_commitments(user: CurrentUser, db: DbSession) -> list[Commitment]:
    return list(db.scalars(select(Commitment).where(Commitment.user_id == user.id).order_by(Commitment.start_at)).all())


@router.post("/commitments", response_model=CommitmentOut, status_code=201)
def create_commitment(payload: CommitmentIn, user: CurrentUser, db: DbSession) -> Commitment:
    commitment = Commitment(user_id=user.id, **payload.model_dump())
    db.add(commitment)
    db.flush()
    schedule.recheck_sessions(db, user)
    db.commit()
    return commitment


@router.put("/commitments/{commitment_id}", response_model=CommitmentOut)
def update_commitment(commitment_id: int, payload: CommitmentIn, user: CurrentUser, db: DbSession) -> Commitment:
    commitment = _own_commitment(db, user.id, commitment_id)
    for field, value in payload.model_dump().items():
        setattr(commitment, field, value)
    db.flush()
    schedule.recheck_sessions(db, user)
    db.commit()
    return commitment


@router.delete("/commitments/{commitment_id}", status_code=204)
def delete_commitment(commitment_id: int, user: CurrentUser, db: DbSession) -> None:
    db.delete(_own_commitment(db, user.id, commitment_id))
    db.flush()
    schedule.recheck_sessions(db, user)
    db.commit()


def _check_requirement_links(db: DbSession, user, payload: RequirementIn) -> None:
    if payload.subject_id is not None:
        content.get_visible_subject(db, user, payload.subject_id)
    if payload.topic_id is not None:
        topic = content.get_visible_topic(db, user, payload.topic_id)
        if payload.subject_id is not None and topic.subject_id != payload.subject_id:
            raise bad_request("invalid_topic", "The topic does not belong to this subject.")


@router.get("/requirements", response_model=list[RequirementOut])
def list_requirements(user: CurrentUser, db: DbSession) -> list[Requirement]:
    return list(db.scalars(select(Requirement).where(Requirement.user_id == user.id).order_by(Requirement.due_at)).all())


@router.post("/requirements", response_model=RequirementOut, status_code=201)
def create_requirement(payload: RequirementIn, user: CurrentUser, db: DbSession) -> Requirement:
    _check_requirement_links(db, user, payload)
    subject_id = payload.subject_id
    if payload.topic_id is not None and subject_id is None:
        subject_id = content.get_visible_topic(db, user, payload.topic_id).subject_id
    requirement = Requirement(
        user_id=user.id, title=payload.title, due_at=payload.due_at, subject_id=subject_id, topic_id=payload.topic_id
    )
    db.add(requirement)
    db.commit()
    return requirement


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut)
def update_requirement(requirement_id: int, payload: RequirementUpdate, user: CurrentUser, db: DbSession) -> Requirement:
    requirement = db.scalar(select(Requirement).where(Requirement.id == requirement_id, Requirement.user_id == user.id))
    if requirement is None:
        raise not_found("Requirement")
    requirement.done = payload.done
    db.commit()
    return requirement


@router.delete("/requirements/{requirement_id}", status_code=204)
def delete_requirement(requirement_id: int, user: CurrentUser, db: DbSession) -> None:
    requirement = db.scalar(select(Requirement).where(Requirement.id == requirement_id, Requirement.user_id == user.id))
    if requirement is None:
        raise not_found("Requirement")
    db.delete(requirement)
    db.commit()


@router.get("/schedule", response_model=ScheduleOut)
def get_schedule(
    user: CurrentUser,
    db: DbSession,
    start: datetime | None = None,
    end: datetime | None = Query(default=None),
) -> ScheduleOut:
    start = start or datetime.combine(now_local().date(), time())
    end = end or start + timedelta(days=7)
    if start.tzinfo or end.tzinfo:
        raise bad_request("invalid_range", "Send local times without a timezone offset.")
    if end <= start or (end - start).days > MAX_RANGE_DAYS:
        raise bad_request("invalid_range", f"Range must be positive and at most {MAX_RANGE_DAYS} days.")

    occurrences = [
        OccurrenceOut(
            commitment_id=commitment.id, title=commitment.title, kind=commitment.kind,
            start_at=interval.start, end_at=interval.end,
        )
        for commitment, interval in schedule.commitment_occurrences(db, user.id, start, end)
    ]
    sessions = db.scalars(
        select(StudySession).where(
            StudySession.user_id == user.id,
            StudySession.status.in_(("scheduled", "needs_reschedule")),
        )
    ).all()
    session_rows: list[SessionOut] = []
    for session in sessions:
        if session.start_at is not None and not (start <= session.start_at < end):
            continue
        recommendation = db.get(Recommendation, session.recommendation_id)
        topic = db.get(Topic, recommendation.topic_id)
        session_rows.append(
            SessionOut(
                id=session.id, recommendation_id=recommendation.id, start_at=session.start_at, end_at=session.end_at,
                status=session.status, topic_name=topic.name, subject_name=db.get(Subject, topic.subject_id).name,
                activity_type=recommendation.activity_type,
            )
        )
    requirements = db.scalars(
        select(Requirement)
        .where(Requirement.user_id == user.id, Requirement.due_at >= start, Requirement.due_at < end)
        .order_by(Requirement.due_at)
    ).all()
    return ScheduleOut(
        commitments=occurrences,
        sessions=session_rows,
        requirements=[RequirementOut.model_validate(r) for r in requirements],
    )


@router.post("/schedule/replan")
def replan(user: CurrentUser, db: DbSession) -> dict[str, int]:
    schedule.recheck_sessions(db, user)
    placed = schedule.replan_unscheduled(db, user)
    db.commit()
    return {"placed": placed}
