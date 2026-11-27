from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now_local
from app.core.errors import not_found
from app.ml.bkt import BKTParams, is_mastered
from app.models import Enrollment, Material, Question, Subject, Topic, TopicMastery, User

MIN_QUESTIONS = 5


def visible_subject_filter(user: User):
    return or_(Subject.owner_id.is_(None), Subject.owner_id == user.id)


def visible_question_filter(user: User):
    return or_(Question.owner_id.is_(None), Question.owner_id == user.id)


def get_visible_subject(db: Session, user: User, subject_id: int) -> Subject:
    subject = db.scalar(select(Subject).where(Subject.id == subject_id, visible_subject_filter(user)))
    if subject is None:
        raise not_found("Subject")
    return subject


def get_visible_topic(db: Session, user: User, topic_id: int) -> Topic:
    topic = db.scalar(
        select(Topic).join(Subject).where(Topic.id == topic_id, visible_subject_filter(user))
    )
    if topic is None:
        raise not_found("Topic")
    return topic


def get_owned_subject(db: Session, user: User, subject_id: int) -> Subject:
    subject = db.scalar(select(Subject).where(Subject.id == subject_id, Subject.owner_id == user.id))
    if subject is None:
        raise not_found("Subject")
    return subject


def is_enrolled(db: Session, user: User, subject_id: int) -> bool:
    return db.scalar(
        select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.subject_id == subject_id)
    ) is not None


def enroll(db: Session, user: User, subject_id: int) -> None:
    if not is_enrolled(db, user, subject_id):
        db.add(Enrollment(user_id=user.id, subject_id=subject_id))


def topic_params(topic: Topic) -> BKTParams:
    return BKTParams(topic.p_l0, topic.p_t, topic.p_g, topic.p_s)


def question_count(db: Session, user: User, topic_id: int) -> int:
    return db.scalar(
        select(func.count(Question.id)).where(Question.topic_id == topic_id, visible_question_filter(user))
    ) or 0


def material_query(user: User, topic: Topic):
    """Materials are private to their uploader; topic-level or subject-level."""
    return select(Material).where(
        Material.uploader_id == user.id,
        Material.subject_id == topic.subject_id,
        or_(Material.topic_id == topic.id, Material.topic_id.is_(None)),
    )


def material_count(db: Session, user: User, topic: Topic) -> int:
    return len(db.scalars(material_query(user, topic)).all())


def get_mastery(db: Session, user: User, topic: Topic) -> TopicMastery:
    row = db.scalar(select(TopicMastery).where(TopicMastery.user_id == user.id, TopicMastery.topic_id == topic.id))
    if row is None:
        row = TopicMastery(user_id=user.id, topic_id=topic.id, p_mastery=topic.p_l0, diagnostic_done=False)
        db.add(row)
        db.flush()
    return row


def touch_activity(row: TopicMastery) -> None:
    row.last_activity_at = now_local()


def topic_ready(db: Session, user: User, topic: Topic) -> bool:
    return question_count(db, user, topic.id) >= MIN_QUESTIONS


def mastery_flag(row: TopicMastery | None) -> bool:
    return row is not None and is_mastered(row.p_mastery)
