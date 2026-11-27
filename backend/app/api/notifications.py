from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbSession
from app.core.clock import now_local
from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.models import Notification, PushSubscription
from app.schemas import NotificationOut, PushSubscribeIn, PushUnsubscribeIn
from app.services import notify

router = APIRouter(tags=["notifications"])


def _visible(user_id: int):
    return (Notification.user_id == user_id, Notification.scheduled_for <= now_local())


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(user: CurrentUser, db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(*_visible(user.id)).order_by(Notification.scheduled_for.desc(), Notification.id.desc()).limit(limit)
        ).all()
    )


@router.get("/notifications/unread-count")
def unread_count(user: CurrentUser, db: DbSession) -> dict[str, int]:
    count = db.scalar(select(func.count(Notification.id)).where(*_visible(user.id), Notification.read_at.is_(None)))
    return {"count": count or 0}


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, user: CurrentUser, db: DbSession) -> None:
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if notification is None:
        raise not_found("Notification")
    if notification.read_at is None:
        notification.read_at = now_local()
        db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(user: CurrentUser, db: DbSession) -> None:
    db.execute(
        update(Notification)
        .where(*_visible(user.id), Notification.read_at.is_(None))
        .values(read_at=now_local())
    )
    db.commit()


@router.get("/push/public-key")
def public_key() -> dict[str, str]:
    if not notify.push_configured():
        raise ApiError(503, "push_unavailable", "Push notifications are not configured on this server.")
    return {"key": get_settings().vapid_public_key}


@router.post("/push/subscribe", status_code=204)
def subscribe(payload: PushSubscribeIn, user: CurrentUser, db: DbSession) -> None:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if existing:
        existing.user_id, existing.p256dh, existing.auth = user.id, payload.keys.p256dh, payload.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=user.id, endpoint=payload.endpoint, p256dh=payload.keys.p256dh, auth=payload.keys.auth
            )
        )
    db.commit()


@router.post("/push/unsubscribe", status_code=204)
def unsubscribe(payload: PushUnsubscribeIn, user: CurrentUser, db: DbSession) -> None:
    subscription = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id)
    )
    if subscription:
        db.delete(subscription)
        db.commit()
