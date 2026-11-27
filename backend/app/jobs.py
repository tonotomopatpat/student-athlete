import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.db import SessionLocal
from app.services import notify

logger = logging.getLogger(__name__)

JOB_INTERVAL_SECONDS = 30


def run_notification_cycle() -> None:
    """Create due reminders, then push any notifications that have come due."""
    db = SessionLocal()
    try:
        notify.generate_due_reminders(db)
        notify.dispatch_push(db)
    except Exception:
        db.rollback()
        logger.exception("Notification cycle failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_notification_cycle,
        "interval",
        seconds=JOB_INTERVAL_SECONDS,
        id="notification-cycle",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
