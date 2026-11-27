from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

_frozen_now: datetime | None = None


def freeze_now(moment: datetime | None) -> None:
    """Pin the clock (tests only). Pass None to resume real time."""
    global _frozen_now
    _frozen_now = moment


def now_local() -> datetime:
    """Current wall-clock time in the campus timezone, as a naive datetime.

    All schedule data is stored as naive local time because the system serves a
    single campus (Asia/Manila).
    """
    if _frozen_now is not None:
        return _frozen_now
    return datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None, microsecond=0)
