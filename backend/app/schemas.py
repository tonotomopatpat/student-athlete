from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

ActivityType = Literal["review_material", "practice", "quiz", "revisit"]
CommitmentKind = Literal["class", "exam", "training", "competition", "travel", "other"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]
    sport: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()


class SettingsIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    sport: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    study_window_start: int | None = Field(default=None, ge=0, le=23 * 60)
    study_window_end: int | None = Field(default=None, ge=60, le=24 * 60)
    buffer_minutes: int | None = Field(default=None, ge=0, le=120)
    reminder_minutes: int | None = Field(default=None, ge=0, le=240)

    @model_validator(mode="after")
    def window_is_ordered(self) -> "SettingsIn":
        if (
            self.study_window_start is not None
            and self.study_window_end is not None
            and self.study_window_end - self.study_window_start < 60
        ):
            raise ValueError("Study window must be at least 60 minutes long.")
        return self


class UserOut(ORM):
    id: int
    email: str
    name: str
    sport: str | None
    study_window_start: int
    study_window_end: int
    buffer_minutes: int
    reminder_minutes: int


class SubjectIn(BaseModel):
    name: Title
    description: LongText = ""


class TopicIn(BaseModel):
    name: Title


class TopicOut(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    name: str
    question_count: int
    ready: bool
    diagnostic_done: bool
    mastery: float | None
    mastered: bool
    material_count: int


class SubjectOut(BaseModel):
    id: int
    code: str | None
    name: str
    description: str
    is_builtin: bool
    is_sample: bool
    enrolled: bool
    topic_count: int


class SubjectDetailOut(SubjectOut):
    topics: list[TopicOut]


class MaterialOut(ORM):
    id: int
    subject_id: int
    topic_id: int | None
    title: str
    kind: str
    body: str
    original_name: str | None
    mime_type: str | None
    created_at: datetime


class MaterialNoteIn(BaseModel):
    subject_id: int
    topic_id: int | None = None
    title: Title
    kind: Literal["note", "link"]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]

    @model_validator(mode="after")
    def link_is_http(self) -> "MaterialNoteIn":
        if self.kind == "link" and not self.body.lower().startswith(("http://", "https://")):
            raise ValueError("Links must start with http:// or https://")
        return self


class QuestionIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    choices: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]] = Field(
        min_length=2, max_length=6
    )
    correct_index: int = Field(ge=0)
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""

    @model_validator(mode="after")
    def valid_key(self) -> "QuestionIn":
        if self.correct_index >= len(self.choices):
            raise ValueError("correct_index must point to one of the choices.")
        if len({c.lower() for c in self.choices}) != len(self.choices):
            raise ValueError("Choices must be different from each other.")
        return self


class QuestionBulkIn(BaseModel):
    text: Annotated[str, StringConstraints(min_length=1, max_length=60000)]


class QuestionOwnOut(ORM):
    id: int
    topic_id: int
    text: str
    choices: list[str]
    correct_index: int
    explanation: str


class QuestionPublic(BaseModel):
    id: int
    text: str
    choices: list[str]


class BulkResult(BaseModel):
    created: int
    errors: list[str]


class AnswerIn(BaseModel):
    question_id: int
    chosen_index: int = Field(ge=0, le=5)


class SubmitIn(BaseModel):
    topic_id: int
    context: Literal["diagnostic", "self"]
    answers: list[AnswerIn] = Field(min_length=1, max_length=40)


class RecommendationSubmitIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=40)


class AnswerResult(BaseModel):
    question_id: int
    correct: bool
    correct_index: int
    explanation: str
    mastery_after: float


class SubmitOut(BaseModel):
    topic_id: int
    mastery_before: float
    mastery_after: float
    correct_count: int
    total: int
    results: list[AnswerResult]
    mastered: bool


class CommitmentIn(BaseModel):
    title: Title
    kind: CommitmentKind
    start_at: datetime
    end_at: datetime
    repeat_weekly: bool = False
    repeat_until: date | None = None

    @model_validator(mode="after")
    def valid_range(self) -> "CommitmentIn":
        if self.start_at.tzinfo or self.end_at.tzinfo:
            raise ValueError("Send local times without a timezone offset.")
        if self.end_at <= self.start_at:
            raise ValueError("End time must be after start time.")
        if (self.end_at - self.start_at).total_seconds() > 24 * 3600:
            raise ValueError("A commitment cannot be longer than 24 hours.")
        if self.repeat_until and self.repeat_until < self.start_at.date():
            raise ValueError("Repeat-until date cannot be before the start date.")
        if self.repeat_until and not self.repeat_weekly:
            raise ValueError("repeat_until requires repeat_weekly.")
        return self


class CommitmentOut(ORM):
    id: int
    title: str
    kind: str
    start_at: datetime
    end_at: datetime
    repeat_weekly: bool
    repeat_until: date | None


class RequirementIn(BaseModel):
    title: Title
    due_at: datetime
    subject_id: int | None = None
    topic_id: int | None = None

    @field_validator("due_at")
    @classmethod
    def naive_due(cls, value: datetime) -> datetime:
        if value.tzinfo:
            raise ValueError("Send local times without a timezone offset.")
        return value


class RequirementUpdate(BaseModel):
    done: bool


class RequirementOut(ORM):
    id: int
    title: str
    due_at: datetime
    subject_id: int | None
    topic_id: int | None
    done: bool


class OccurrenceOut(BaseModel):
    commitment_id: int
    title: str
    kind: str
    start_at: datetime
    end_at: datetime


class SessionOut(BaseModel):
    id: int
    recommendation_id: int
    start_at: datetime | None
    end_at: datetime | None
    status: str
    topic_name: str
    subject_name: str
    activity_type: str


class ScheduleOut(BaseModel):
    commitments: list[OccurrenceOut]
    sessions: list[SessionOut]
    requirements: list[RequirementOut]


class RecommendationOut(BaseModel):
    id: int
    topic_id: int
    topic_name: str
    subject_name: str
    activity_type: str
    reason: str
    status: str
    duration_minutes: int
    start_at: datetime | None
    end_at: datetime | None
    session_status: str | None
    explored: bool
    created_at: datetime


class ActivityMaterial(BaseModel):
    id: int
    title: str
    kind: str
    body: str


class ActivityStartOut(BaseModel):
    recommendation: RecommendationOut
    materials: list[ActivityMaterial]
    questions: list[QuestionPublic]


class CompleteOut(BaseModel):
    recommendation: RecommendationOut
    reward: float
    mastery_before: float
    mastery_after: float


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: str
    link: str | None
    scheduled_for: datetime
    read_at: datetime | None


class PushKeysIn(BaseModel):
    p256dh: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    auth: Annotated[str, StringConstraints(min_length=1, max_length=255)]


class PushSubscribeIn(BaseModel):
    endpoint: Annotated[str, StringConstraints(min_length=10, max_length=600)]
    keys: PushKeysIn

    @field_validator("endpoint")
    @classmethod
    def https_endpoint(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Push endpoint must use https.")
        return value


class PushUnsubscribeIn(BaseModel):
    endpoint: Annotated[str, StringConstraints(min_length=10, max_length=600)]


class ProgressTopicOut(BaseModel):
    topic_id: int
    topic_name: str
    subject_name: str
    mastery: float
    mastered: bool
    responses: int
    correct: int


class MasteryPoint(BaseModel):
    at: datetime
    mastery: float
    correct: bool


class ProgressHistoryOut(BaseModel):
    topic_id: int
    points: list[MasteryPoint]
