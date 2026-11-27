"""Pure scheduling logic: expand commitments, find free study slots, place activities.

Deterministic and free of database access so it can be tested with fixed inputs.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

SLOT_ROUNDING_MINUTES = 5
MIN_SLOT_MINUTES = 15


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class CommitmentRule:
    start_at: datetime
    end_at: datetime
    repeat_weekly: bool = False
    repeat_until: date | None = None


def expand_commitment(rule: CommitmentRule, window_start: datetime, window_end: datetime) -> list[Interval]:
    """Occurrences of a (possibly weekly-recurring) commitment overlapping the window."""
    duration = rule.end_at - rule.start_at
    occurrences: list[Interval] = []
    if not rule.repeat_weekly:
        interval = Interval(rule.start_at, rule.end_at)
        if interval.overlaps(Interval(window_start, window_end)):
            occurrences.append(interval)
        return occurrences
    weeks_before = max(0, math.floor((window_start - rule.end_at).total_seconds() / (7 * 86400)))
    start = rule.start_at + timedelta(weeks=weeks_before)
    while start < window_end:
        if rule.repeat_until is not None and start.date() > rule.repeat_until:
            break
        interval = Interval(start, start + duration)
        if interval.overlaps(Interval(window_start, window_end)):
            occurrences.append(interval)
        start += timedelta(weeks=1)
    return occurrences


def _round_up(moment: datetime) -> datetime:
    rounded = moment.replace(second=0, microsecond=0)
    if moment.second or moment.microsecond:
        rounded += timedelta(minutes=1)
    return rounded + timedelta(minutes=(SLOT_ROUNDING_MINUTES - rounded.minute % SLOT_ROUNDING_MINUTES) % SLOT_ROUNDING_MINUTES)


def _merge(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for interval in sorted(intervals, key=lambda i: i.start):
        if merged and interval.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, interval.end))
        else:
            merged.append(interval)
    return merged


def free_slots(
    busy: Iterable[Interval],
    window_start: datetime,
    window_end: datetime,
    study_start_minute: int,
    study_end_minute: int,
    buffer_minutes: int,
    min_minutes: int = MIN_SLOT_MINUTES,
) -> list[Interval]:
    """Gaps inside the daily study window that are clear of busy intervals plus buffer."""
    buffer = timedelta(minutes=buffer_minutes)
    padded = _merge(Interval(b.start - buffer, b.end + buffer) for b in busy)
    allowed: list[Interval] = []
    day = window_start.date()
    while day <= window_end.date():
        base = datetime.combine(day, time())
        start = max(base + timedelta(minutes=study_start_minute), window_start)
        end = min(base + timedelta(minutes=study_end_minute), window_end)
        if end > start:
            allowed.append(Interval(start, end))
        day += timedelta(days=1)

    slots: list[Interval] = []
    for window in allowed:
        cursor = window.start
        for block in padded:
            if block.end <= cursor or block.start >= window.end:
                continue
            if block.start > cursor:
                slots.append(Interval(cursor, block.start))
            cursor = max(cursor, block.end)
        if cursor < window.end:
            slots.append(Interval(cursor, window.end))

    rounded: list[Interval] = []
    for slot in slots:
        start = _round_up(slot.start)
        if (slot.end - start).total_seconds() / 60.0 >= min_minutes:
            rounded.append(Interval(start, slot.end))
    return rounded


def find_slot(slots: Iterable[Interval], duration_minutes: int, not_before: datetime) -> Interval | None:
    """Earliest placement of an activity of the given length, or None if nothing fits."""
    needed = timedelta(minutes=duration_minutes)
    for slot in sorted(slots, key=lambda s: s.start):
        start = _round_up(max(slot.start, not_before))
        if start + needed <= slot.end:
            return Interval(start, start + needed)
    return None


def available_minutes(slots: Iterable[Interval], not_before: datetime) -> float:
    """Length of the next free slot at or after `not_before` (0 if none)."""
    for slot in sorted(slots, key=lambda s: s.start):
        start = max(slot.start, not_before)
        if slot.end > start:
            return (slot.end - start).total_seconds() / 60.0
    return 0.0
