import json
import logging
from datetime import datetime, timedelta

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import now_local
from app.core.config import get_settings
from app.models import Notification, PushSubscription, Recommendation, Requirement, StudySession, Topic, User

logger = logging.getLogger(__name__)

REMINDER_LOOKAHEAD = timedelta(hours=24)
MAX_PUSH_AGE = timedelta(hours=1)
PUSH_TIMEOUT_SECONDS = 10


def create(
    db: Session,
    user_id: int,
    event_key: str,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
    scheduled_for: datetime | None = None,
) -> Notification | None:
    """Idempotent: a repeated (user, event_key) pair never creates a second notification."""
    exists = db.scalar(
        select(Notification.id).where(Notification.user_id == user_id, Notification.event_key == event_key)
    )
    if exists:
        return None
    notification = Notification(
        user_id=user_id,
        event_key=event_key,
        kind=kind,
        title=title,
        body=body,
        link=link,
        scheduled_for=scheduled_for or now_local(),
    )
    try:
        with db.begin_nested():
            db.add(notification)
    except IntegrityError:
        return None
    return notification


def generate_due_reminders(db: Session, now: datetime | None = None) -> int:
    now = now or now_local()
    created = 0
    sessions = db.scalars(
        select(StudySession).where(
            StudySession.status == "scheduled",
            StudySession.start_at > now,
            StudySession.start_at <= now + REMINDER_LOOKAHEAD,
        )
    ).all()
    for session in sessions:
        user = db.get(User, session.user_id)
        recommendation = db.get(Recommendation, session.recommendation_id)
        topic = db.get(Topic, recommendation.topic_id)
        fire_at = max(now, session.start_at - timedelta(minutes=user.reminder_minutes))
        notification = create(
            db,
            user.id,
            f"session:{session.id}:{session.start_at.isoformat()}:reminder",
            "session_reminder",
            "Study session coming up",
            f"{recommendation.activity_type.replace('_', ' ').title()}: {topic.name} at {session.start_at:%I:%M %p}.",
            f"/activity/{recommendation.id}",
            scheduled_for=fire_at,
        )
        created += notification is not None

    requirements = db.scalars(
        select(Requirement).where(
            Requirement.done.is_(False), Requirement.due_at > now, Requirement.due_at <= now + REMINDER_LOOKAHEAD
        )
    ).all()
    for requirement in requirements:
        notification = create(
            db,
            requirement.user_id,
            f"deadline:{requirement.id}:{requirement.due_at.isoformat()}:24h",
            "deadline",
            "Deadline within 24 hours",
            f"{requirement.title} is due {requirement.due_at:%a %b %d, %I:%M %p}.",
            "/plan",
            scheduled_for=now,
        )
        created += notification is not None
    db.commit()
    return created


def push_configured() -> bool:
    settings = get_settings()
    return bool(settings.vapid_private_key and settings.vapid_public_key)


def _send(subscription: PushSubscription, notification: Notification) -> bool | None:
    """Returns True on success, False if the subscription is gone, None on other failures."""
    settings = get_settings()
    payload = json.dumps({"title": notification.title, "body": notification.body, "link": notification.link or "/today"})
    try:
        webpush(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            timeout=PUSH_TIMEOUT_SECONDS,
        )
        return True
    except WebPushException as error:
        status = error.response.status_code if error.response is not None else None
        if status in (404, 410):
            return False
        logger.warning("Web push failed for notification %s (status %s)", notification.id, status)
        return None
    except Exception:
        logger.warning("Web push error for notification %s", notification.id, exc_info=True)
        return None


def dispatch_push(db: Session, now: datetime | None = None) -> int:
    """Send due notifications as Web Push. In-app delivery does not depend on this."""
    now = now or now_local()
    due = db.scalars(
        select(Notification).where(Notification.pushed_at.is_(None), Notification.scheduled_for <= now)
    ).all()
    sent = 0
    for notification in due:
        notification.pushed_at = now
        if not push_configured() or now - notification.scheduled_for > MAX_PUSH_AGE:
            continue
        subscriptions = db.scalars(select(PushSubscription).where(PushSubscription.user_id == notification.user_id)).all()
        for subscription in subscriptions:
            outcome = _send(subscription, notification)
            if outcome is False:
                db.delete(subscription)
            elif outcome:
                sent += 1
    db.commit()
    return sent
