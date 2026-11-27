from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.ml.bkt import is_mastered
from app.models import Response, Subject, Topic, TopicMastery
from app.schemas import MasteryPoint, ProgressHistoryOut, ProgressTopicOut
from app.services import content

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("", response_model=list[ProgressTopicOut])
def progress(user: CurrentUser, db: DbSession) -> list[ProgressTopicOut]:
    rows = db.execute(
        select(TopicMastery, Topic, Subject)
        .join(Topic, TopicMastery.topic_id == Topic.id)
        .join(Subject, Topic.subject_id == Subject.id)
        .where(TopicMastery.user_id == user.id, TopicMastery.diagnostic_done.is_(True))
        .order_by(Subject.name, Topic.position)
    ).all()
    correct_by_topic = dict(
        db.execute(
            select(Response.topic_id, func.count(Response.id))
            .where(Response.user_id == user.id, Response.correct.is_(True))
            .group_by(Response.topic_id)
        ).all()
    )
    return [
        ProgressTopicOut(
            topic_id=topic.id,
            topic_name=topic.name,
            subject_name=subject.name,
            mastery=mastery.p_mastery,
            mastered=is_mastered(mastery.p_mastery),
            responses=mastery.response_count,
            correct=correct_by_topic.get(topic.id, 0),
        )
        for mastery, topic, subject in rows
    ]


@router.get("/topics/{topic_id}", response_model=ProgressHistoryOut)
def history(topic_id: int, user: CurrentUser, db: DbSession, limit: int = Query(default=200, ge=1, le=1000)) -> ProgressHistoryOut:
    topic = content.get_visible_topic(db, user, topic_id)
    responses = db.scalars(
        select(Response)
        .where(Response.user_id == user.id, Response.topic_id == topic.id)
        .order_by(Response.id.desc())
        .limit(limit)
    ).all()
    points = [MasteryPoint(at=r.created_at, mastery=r.mastery_after, correct=r.correct) for r in reversed(responses)]
    return ProgressHistoryOut(topic_id=topic.id, points=points)
