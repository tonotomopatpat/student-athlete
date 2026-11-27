from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.assessments import result_payload
from app.api.deps import CurrentUser, DbSession
from app.models import Recommendation, Subject, Topic
from app.schemas import (
    ActivityMaterial,
    ActivityStartOut,
    CompleteOut,
    QuestionPublic,
    RecommendationOut,
    RecommendationSubmitIn,
    SubmitOut,
)
from app.services import recommender

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def to_out(db: DbSession, recommendation: Recommendation) -> RecommendationOut:
    topic = db.get(Topic, recommendation.topic_id)
    subject = db.get(Subject, topic.subject_id)
    session = recommendation.session
    return RecommendationOut(
        id=recommendation.id,
        topic_id=topic.id,
        topic_name=topic.name,
        subject_name=subject.name,
        activity_type=recommendation.activity_type,
        reason=recommender.reason_text(recommendation),
        status=recommendation.status,
        duration_minutes=recommender.duration_minutes(recommendation),
        start_at=session.start_at if session else None,
        end_at=session.end_at if session else None,
        session_status=session.status if session else None,
        explored=recommendation.explored,
        created_at=recommendation.created_at,
    )


@router.post("/next", response_model=RecommendationOut)
def next_recommendation(user: CurrentUser, db: DbSession) -> RecommendationOut:
    return to_out(db, recommender.next_recommendation(db, user))


@router.get("/current", response_model=RecommendationOut | None)
def current(user: CurrentUser, db: DbSession) -> RecommendationOut | None:
    recommendation = recommender.current_open(db, user)
    return to_out(db, recommendation) if recommendation else None


@router.get("", response_model=list[RecommendationOut])
def history(user: CurrentUser, db: DbSession, limit: int = Query(default=20, ge=1, le=100)) -> list[RecommendationOut]:
    rows = db.scalars(
        select(Recommendation).where(Recommendation.user_id == user.id).order_by(Recommendation.id.desc()).limit(limit)
    ).all()
    return [to_out(db, r) for r in rows]


@router.get("/{recommendation_id}", response_model=RecommendationOut)
def get_one(recommendation_id: int, user: CurrentUser, db: DbSession) -> RecommendationOut:
    return to_out(db, recommender.get_recommendation(db, user, recommendation_id))


@router.post("/{recommendation_id}/start", response_model=ActivityStartOut)
def start(recommendation_id: int, user: CurrentUser, db: DbSession) -> ActivityStartOut:
    recommendation = recommender.get_recommendation(db, user, recommendation_id)
    materials, questions = recommender.start_activity(db, user, recommendation)
    return ActivityStartOut(
        recommendation=to_out(db, recommendation),
        materials=[ActivityMaterial(id=m.id, title=m.title, kind=m.kind, body=m.body) for m in materials],
        questions=[QuestionPublic(id=q.id, text=q.text, choices=q.choices) for q in questions],
    )


@router.post("/{recommendation_id}/complete", response_model=CompleteOut)
def complete_review(recommendation_id: int, user: CurrentUser, db: DbSession) -> CompleteOut:
    recommendation = recommender.get_recommendation(db, user, recommendation_id)
    reward = recommender.complete_review(db, user, recommendation)
    return CompleteOut(
        recommendation=to_out(db, recommendation),
        reward=reward,
        mastery_before=recommendation.mastery_before,
        mastery_after=recommendation.mastery_after,
    )


@router.post("/{recommendation_id}/submit", response_model=SubmitOut)
def submit(recommendation_id: int, payload: RecommendationSubmitIn, user: CurrentUser, db: DbSession) -> SubmitOut:
    recommendation = recommender.get_recommendation(db, user, recommendation_id)
    result, _ = recommender.complete_with_answers(db, user, recommendation, payload.answers)
    return result_payload(recommendation.topic_id, result)


@router.post("/{recommendation_id}/skip", response_model=CompleteOut)
def skip(recommendation_id: int, user: CurrentUser, db: DbSession) -> CompleteOut:
    recommendation = recommender.get_recommendation(db, user, recommendation_id)
    reward = recommender.skip(db, user, recommendation)
    return CompleteOut(
        recommendation=to_out(db, recommendation),
        reward=reward,
        mastery_before=recommendation.mastery_before,
        mastery_after=recommendation.mastery_after,
    )
