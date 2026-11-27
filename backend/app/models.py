from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now_local
from app.core.db import Base

# MySQL DATETIME drops fractional seconds and FLOAT is single precision; keep both exact.
Timestamp = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
# MySQL TEXT holds only 64 KB; extracted lessons need more.
LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")

COMMITMENT_KINDS = ("class", "exam", "training", "competition", "travel", "other")
ACTIVITY_TYPES = ("review_material", "practice", "quiz", "revisit")
SESSION_STATUSES = ("scheduled", "completed", "skipped", "needs_reschedule")
RECOMMENDATION_STATUSES = ("pending", "started", "completed", "skipped")
RESPONSE_CONTEXTS = ("diagnostic", "practice", "quiz", "revisit", "self")
EXTRACTION_STATUSES = ("pending", "ok", "failed", "needs_review")
GENERATION_JOB_STATUSES = ("queued", "running", "done", "failed")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    sport: Mapped[str | None] = mapped_column(String(80), nullable=True)
    study_window_start: Mapped[int] = mapped_column(Integer, default=6 * 60)
    study_window_end: Mapped[int] = mapped_column(Integer, default=22 * 60)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    reminder_minutes: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now_local)


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    topics: Mapped[list["Topic"]] = relationship(back_populates="subject", order_by="Topic.position", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("subject_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    position: Mapped[int] = mapped_column(Integer, default=0)
    p_l0: Mapped[float] = mapped_column(Double, default=0.20)
    p_t: Mapped[float] = mapped_column(Double, default=0.15)
    p_g: Mapped[float] = mapped_column(Double, default=0.25)
    p_s: Mapped[float] = mapped_column(Double, default=0.10)
    subject: Mapped[Subject] = relationship(back_populates="topics")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[str]] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, default="")
    is_diagnostic: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text, default="")
    stored_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now_local)
    extracted_text: Mapped[str | None] = mapped_column(LongText, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    extraction_error: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sections: Mapped[list["MaterialSection"]] = relationship(
        back_populates="material", order_by="MaterialSection.position", cascade="all, delete-orphan"
    )


class MaterialSection(Base):
    """A heading-delimited part of a material's extracted text, routed to one of the subject's topics."""

    __tablename__ = "material_sections"
    __table_args__ = (UniqueConstraint("material_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300), default="")
    level: Mapped[int] = mapped_column(Integer, default=0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True)
    score: Mapped[float] = mapped_column(Double, default=0.0)
    assigned_by: Mapped[str] = mapped_column(String(10), default="auto")
    material: Mapped[Material] = relationship(back_populates="sections")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now_local, index=True)
    started_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)


class TopicMastery(Base):
    __tablename__ = "topic_mastery"
    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    p_mastery: Mapped[float] = mapped_column(Double)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    diagnostic_done: Mapped[bool] = mapped_column(Boolean, default=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True)
    context: Mapped[str] = mapped_column(String(20))
    chosen_index: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean)
    mastery_before: Mapped[float] = mapped_column(Double)
    mastery_after: Mapped[float] = mapped_column(Double)
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now_local)


class Commitment(Base):
    __tablename__ = "commitments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    start_at: Mapped[datetime] = mapped_column(Timestamp)
    end_at: Mapped[datetime] = mapped_column(Timestamp)
    repeat_weekly: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class Requirement(Base):
    """Academic requirement with a deadline (assignment, quiz, exam)."""

    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    due_at: Mapped[datetime] = mapped_column(Timestamp)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class QCell(Base):
    """Shared Q-table entry (one row per state-action pair)."""

    __tablename__ = "q_cells"

    state: Mapped[str] = mapped_column(String(30), primary_key=True)
    action: Mapped[str] = mapped_column(String(30), primary_key=True)
    q_value: Mapped[float] = mapped_column(Double)
    visits: Mapped[int] = mapped_column(Integer, default=0)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    activity_type: Mapped[str] = mapped_column(String(30))
    state_key: Mapped[str] = mapped_column(String(30))
    q_value: Mapped[float] = mapped_column(Double)
    explored: Mapped[bool] = mapped_column(Boolean, default=False)
    epsilon: Mapped[float] = mapped_column(Double)
    available_minutes: Mapped[float] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    mastery_before: Mapped[float | None] = mapped_column(Double, nullable=True)
    mastery_after: Mapped[float | None] = mapped_column(Double, nullable=True)
    reward: Mapped[float | None] = mapped_column(Double, nullable=True)
    next_state_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    q_value_after: Mapped[float | None] = mapped_column(Double, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now_local)
    completed_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    session: Mapped["StudySession | None"] = relationship(back_populates="recommendation", uselist=False)


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), unique=True)
    start_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    recommendation: Mapped[Recommendation] = relationship(back_populates="session")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "event_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scheduled_for: Mapped[datetime] = mapped_column(Timestamp, default=now_local)
    pushed_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=now_local)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(600), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
