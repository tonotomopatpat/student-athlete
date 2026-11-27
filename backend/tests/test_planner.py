from datetime import date, datetime, timedelta

from app.scheduling.planner import (
    CommitmentRule,
    Interval,
    available_minutes,
    expand_commitment,
    find_slot,
    free_slots,
)

MON = datetime(2026, 3, 2)


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 2, hour, minute) + timedelta(days=day_offset)


def day_busy():
    return [Interval(at(0, 8), at(0, 10)), Interval(at(0, 16), at(0, 18))]


def test_free_slots_exclude_commitments_and_buffer():
    slots = free_slots(day_busy(), at(0, 6), at(0, 23), 6 * 60, 22 * 60, buffer_minutes=15)
    assert [(s.start, s.end) for s in slots] == [
        (at(0, 6), at(0, 7, 45)),
        (at(0, 10, 15), at(0, 15, 45)),
        (at(0, 18, 15), at(0, 22)),
    ]


def test_no_slot_overlaps_any_commitment():
    busy = day_busy()
    for slot in free_slots(busy, at(0, 0), at(2, 0), 6 * 60, 22 * 60, 0):
        assert not any(slot.overlaps(b) for b in busy)


def test_slots_shorter_than_minimum_are_dropped():
    busy = [Interval(at(0, 6, 10), at(0, 21, 50))]
    assert free_slots(busy, at(0, 6), at(0, 22), 6 * 60, 22 * 60, 0) == []


def test_window_start_clips_past_time():
    slots = free_slots([], at(0, 9, 3), at(0, 12), 6 * 60, 22 * 60, 0)
    assert slots[0].start == at(0, 9, 5)


def test_find_slot_respects_duration():
    slots = free_slots(day_busy(), at(0, 6), at(0, 23), 6 * 60, 22 * 60, 15)
    placed = find_slot(slots, 120, at(0, 6))
    assert placed == Interval(at(0, 10, 15), at(0, 12, 15))


def test_find_slot_respects_not_before():
    slots = free_slots([], at(0, 6), at(0, 23), 6 * 60, 22 * 60, 0)
    assert find_slot(slots, 30, at(0, 13, 2)).start == at(0, 13, 5)


def test_find_slot_returns_none_when_nothing_fits():
    slots = free_slots(day_busy(), at(0, 6), at(0, 23), 6 * 60, 22 * 60, 15)
    assert find_slot(slots, 8 * 60, at(0, 6)) is None
    assert find_slot([], 15, at(0, 6)) is None


def test_available_minutes_is_next_slot_length():
    slots = free_slots(day_busy(), at(0, 6), at(0, 23), 6 * 60, 22 * 60, 15)
    assert available_minutes(slots, at(0, 6)) == 105
    assert available_minutes(slots, at(0, 8, 30)) == 330
    assert available_minutes([], at(0, 6)) == 0


def test_weekly_commitment_expansion_and_end_date():
    rule = CommitmentRule(at(0, 8), at(0, 10), repeat_weekly=True, repeat_until=date(2026, 3, 16))
    occurrences = expand_commitment(rule, at(0, 0), at(30, 0))
    assert [o.start for o in occurrences] == [at(0, 8), at(7, 8), at(14, 8)]


def test_weekly_commitment_found_far_in_the_future():
    rule = CommitmentRule(at(0, 8), at(0, 10), repeat_weekly=True)
    occurrences = expand_commitment(rule, at(70, 0), at(77, 0))
    assert [o.start for o in occurrences] == [at(70, 8)]


def test_one_off_commitment_outside_window_is_ignored():
    rule = CommitmentRule(at(0, 8), at(0, 10))
    assert expand_commitment(rule, at(1, 0), at(2, 0)) == []


def test_overnight_commitment_blocks_next_morning():
    busy = [Interval(at(0, 22), at(1, 7))]
    slots = free_slots(busy, at(1, 0), at(1, 12), 6 * 60, 22 * 60, 0)
    assert slots[0].start == at(1, 7)
