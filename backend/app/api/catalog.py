from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.errors import conflict
from app.models import Enrollment, Subject, Topic, TopicMastery, User
from app.schemas import SubjectDetailOut, SubjectIn, SubjectOut, TopicIn, TopicOut
from app.services import content
from app.services.materials import delete_stored_files_for_subject

router = APIRouter(tags=["catalog"])


def _subject_out(db: DbSession, user: User, subject: Subject, enrolled: bool | None = None) -> SubjectOut:
    topic_count = db.scalar(select(func.count(Topic.id)).where(Topic.subject_id == subject.id)) or 0
    return SubjectOut(
        id=subject.id,
        code=subject.code,
        name=subject.name,
        description=subject.description,
        is_builtin=subject.owner_id is None,
        is_sample=subject.is_sample,
        enrolled=content.is_enrolled(db, user, subject.id) if enrolled is None else enrolled,
        topic_count=topic_count,
    )


def _topic_out(db: DbSession, user: User, topic: Topic) -> TopicOut:
    row = db.scalar(select(TopicMastery).where(TopicMastery.user_id == user.id, TopicMastery.topic_id == topic.id))
    count = content.question_count(db, user, topic.id)
    return TopicOut(
        id=topic.id,
        subject_id=topic.subject_id,
        subject_name=db.scalar(select(Subject.name).where(Subject.id == topic.subject_id)) or "",
        name=topic.name,
        question_count=count,
        ready=count >= content.MIN_QUESTIONS,
        diagnostic_done=bool(row and row.diagnostic_done),
        mastery=row.p_mastery if row else None,
        mastered=content.mastery_flag(row),
        material_count=content.material_count(db, user, topic),
    )


def subject_detail(db: DbSession, user: User, subject: Subject) -> SubjectDetailOut:
    base = _subject_out(db, user, subject)
    topics = db.scalars(select(Topic).where(Topic.subject_id == subject.id).order_by(Topic.position, Topic.id)).all()
    return SubjectDetailOut(**base.model_dump(), topics=[_topic_out(db, user, t) for t in topics])


@router.get("/subjects", response_model=list[SubjectOut])
def list_subjects(user: CurrentUser, db: DbSession) -> list[SubjectOut]:
    subjects = db.scalars(
        select(Subject).where(content.visible_subject_filter(user)).order_by(Subject.owner_id.is_not(None), Subject.name)
    ).all()
    enrolled_ids = set(db.scalars(select(Enrollment.subject_id).where(Enrollment.user_id == user.id)).all())
    return [_subject_out(db, user, s, s.id in enrolled_ids) for s in subjects]


@router.get("/overview", response_model=list[SubjectDetailOut])
def overview(user: CurrentUser, db: DbSession) -> list[SubjectDetailOut]:
    """Enrolled subjects with their topics and the student's status on each."""
    subjects = db.scalars(
        select(Subject)
        .join(Enrollment, (Enrollment.subject_id == Subject.id) & (Enrollment.user_id == user.id))
        .where(content.visible_subject_filter(user))
        .order_by(Subject.owner_id.is_not(None), Subject.name)
    ).all()
    return [subject_detail(db, user, s) for s in subjects]


@router.post("/subjects", response_model=SubjectDetailOut, status_code=201)
def create_subject(payload: SubjectIn, user: CurrentUser, db: DbSession) -> SubjectDetailOut:
    duplicate = db.scalar(
        select(Subject.id).where(Subject.owner_id == user.id, func.lower(Subject.name) == payload.name.lower())
    )
    if duplicate:
        raise conflict("subject_exists", "You already have a subject with this name.")
    subject = Subject(name=payload.name, description=payload.description, owner_id=user.id)
    db.add(subject)
    db.flush()
    content.enroll(db, user, subject.id)
    db.commit()
    return subject_detail(db, user, subject)


@router.get("/subjects/{subject_id}", response_model=SubjectDetailOut)
def get_subject(subject_id: int, user: CurrentUser, db: DbSession) -> SubjectDetailOut:
    return subject_detail(db, user, content.get_visible_subject(db, user, subject_id))


@router.delete("/subjects/{subject_id}", status_code=204)
def delete_subject(subject_id: int, user: CurrentUser, db: DbSession) -> None:
    subject = content.get_owned_subject(db, user, subject_id)
    delete_stored_files_for_subject(db, subject.id)
    db.delete(subject)
    db.commit()


@router.post("/subjects/{subject_id}/enroll", response_model=SubjectOut)
def enroll_subject(subject_id: int, user: CurrentUser, db: DbSession) -> SubjectOut:
    subject = content.get_visible_subject(db, user, subject_id)
    content.enroll(db, user, subject.id)
    db.commit()
    return _subject_out(db, user, subject, True)


@router.delete("/subjects/{subject_id}/enroll", response_model=SubjectOut)
def unenroll_subject(subject_id: int, user: CurrentUser, db: DbSession) -> SubjectOut:
    subject = content.get_visible_subject(db, user, subject_id)
    if subject.owner_id == user.id:
        raise conflict("own_subject", "Delete your own subject instead of leaving it.")
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.subject_id == subject.id)
    )
    if enrollment:
        db.delete(enrollment)
        db.commit()
    return _subject_out(db, user, subject, False)


@router.post("/subjects/{subject_id}/topics", response_model=TopicOut, status_code=201)
def create_topic(subject_id: int, payload: TopicIn, user: CurrentUser, db: DbSession) -> TopicOut:
    subject = content.get_owned_subject(db, user, subject_id)
    if db.scalar(select(Topic.id).where(Topic.subject_id == subject.id, func.lower(Topic.name) == payload.name.lower())):
        raise conflict("topic_exists", "This subject already has a topic with that name.")
    position = (db.scalar(select(func.max(Topic.position)).where(Topic.subject_id == subject.id)) or 0) + 1
    topic = Topic(subject_id=subject.id, name=payload.name, position=position)
    db.add(topic)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("topic_exists", "This subject already has a topic with that name.")
    return _topic_out(db, user, topic)


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, user: CurrentUser, db: DbSession) -> None:
    topic = content.get_visible_topic(db, user, topic_id)
    content.get_owned_subject(db, user, topic.subject_id)
    db.delete(topic)
    db.commit()


@router.get("/topics/{topic_id}", response_model=TopicOut)
def get_topic(topic_id: int, user: CurrentUser, db: DbSession) -> TopicOut:
    return _topic_out(db, user, content.get_visible_topic(db, user, topic_id))
