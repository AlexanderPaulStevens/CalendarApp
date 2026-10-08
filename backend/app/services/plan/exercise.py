"""Auto exercise repair, place, and light hour recovery."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from datetime import timezone

from app.rules import access as rules_access
from app.schemas import models
from app.services.plan import events as plan_events
from app.services.plan import params as plan_params
from app.services.plan import summary as plan_summary


def _exercise_count_on_date(
    event_list: list[models.Event],
    day: date,
    zone: ZoneInfo | timezone,
) -> int:
    return sum(
        1
        for e in event_list
        if e.type == models.EventType.EXERCISE
        and plan_events.as_local(e.start, zone).date() == day
    )


def _exercise_hours_on_date(
    event_list: list[models.Event],
    day: date,
    zone: ZoneInfo | timezone,
) -> float:
    return sum(
        plan_events.hours_between(e.start, e.end)
        for e in event_list
        if e.type == models.EventType.EXERCISE
        and plan_events.as_local(e.start, zone).date() == day
    )


def _no_morning_weekdays(ex: dict[str, Any]) -> set[int]:
    raw = ex.get("no_morning_weekdays")
    if not isinstance(raw, list):
        raw = [0, 3]
    return {int(x) for x in raw}


def _exercise_window_for_activity(
    local_day: date,
    activity: models.Activity,
    ex: dict[str, Any],
    zone: ZoneInfo | timezone,
) -> tuple[datetime, datetime] | None:
    earliest = max(0, min(23, plan_params.as_int(ex, "exercise_earliest_hour", 7)))
    morning_end = max(
        earliest + 1, min(23, plan_params.as_int(ex, "morning_end_hour", 12))
    )
    cycling_latest = max(
        morning_end,
        min(24, plan_params.as_int(ex, "cycling_latest_end_hour", 20)),
    )
    day_end_h = 22

    if activity == models.Activity.CYCLING:
        start_h = morning_end
        end_h = min(day_end_h, cycling_latest)
    else:
        if local_day.weekday() in _no_morning_weekdays(ex):
            start_h = morning_end
        else:
            start_h = earliest
        end_h = day_end_h

    if end_h <= start_h:
        return None
    return (
        datetime(
            local_day.year, local_day.month, local_day.day, start_h, 0,
            tzinfo=zone,
        ),
        datetime(
            local_day.year, local_day.month, local_day.day, end_h, 0,
            tzinfo=zone,
        ),
    )


def _preferred_exercise_start(
    local_day: date,
    activity: models.Activity,
    window_start: datetime,
    floor: datetime,
    ex: dict[str, Any],
    zone: ZoneInfo | timezone,
) -> datetime:
    earliest = max(0, min(23, plan_params.as_int(ex, "exercise_earliest_hour", 7)))
    morning_end = max(
        earliest + 1, min(23, plan_params.as_int(ex, "morning_end_hour", 12))
    )
    evening_start = max(
        morning_end, min(22, plan_params.as_int(ex, "evening_start_hour", 17))
    )
    if local_day.weekday() >= 5 and activity == models.Activity.GYM:
        preferred_h = max(earliest, 9)
    elif local_day.weekday() >= 5:
        preferred_h = max(morning_end, 9)
    else:
        preferred_h = evening_start
    preferred = datetime(
        local_day.year,
        local_day.month,
        local_day.day,
        preferred_h,
        0,
        tzinfo=zone,
    )
    return max(floor, window_start, preferred)


def _try_place_exercise(
    local_day: date,
    duration_h: float,
    event_list: list[models.Event],
    now: datetime,
    activity: models.Activity,
    ex: dict[str, Any],
    zone: ZoneInfo | timezone,
) -> tuple[datetime, datetime] | None:
    window = _exercise_window_for_activity(local_day, activity, ex, zone)
    if window is None:
        return None
    ds, de = window
    if de <= now:
        return None
    floor = (
        max(ds, now)
        if local_day == plan_events.as_local(now, zone).date()
        else ds
    )
    if floor >= de:
        return None
    preferred = _preferred_exercise_start(
        local_day, activity, ds, floor, ex, zone
    )
    if preferred >= de:
        preferred = floor
    return plan_events.find_non_overlapping_slot(
        preferred, timedelta(hours=duration_h), event_list, floor, de
    )


def _candidate_exercise_days(
    week_start: datetime,
    week_end: datetime,
    zone: ZoneInfo | timezone,
    now: datetime,
) -> list[date]:
    days: list[date] = []
    d = plan_events.as_local(week_start, zone).date()
    end = plan_events.as_local(week_end - timedelta(seconds=1), zone).date()
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    today = plan_events.as_local(now, zone).date()
    return [x for x in days if x >= today]


def repair(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Move Auto exercise out of conflicts; never move User exercise."""
    zone = plan_events.tz(state)
    ex = rules_access.rule_params(state, models.RuleKey.WEEKLY_EXERCISE_GOAL)
    max_blocks = plan_params.as_int(ex, "max_exercise_blocks_per_day", 1)
    max_hours = plan_params.as_float(ex, "max_exercise_hours_per_day", 3.0)
    state = state.model_copy(deep=True)

    auto_ex = sorted(
        [
            e
            for e in state.events
            if e.type == models.EventType.EXERCISE
            and e.origin == models.Origin.AUTO
            and e.start < week_end
            and e.end > week_start
        ],
        key=lambda e: (e.start, e.id),
    )
    placed = [
        e
        for e in state.events
        if not (
            e.type == models.EventType.EXERCISE
            and e.origin == models.Origin.AUTO
            and e.start < week_end
            and e.end > week_start
        )
    ]
    day_counts: dict[date, int] = defaultdict(int)
    day_hours: dict[date, float] = defaultdict(float)
    for e in placed:
        if e.type != models.EventType.EXERCISE:
            continue
        local_day = plan_events.as_local(e.start, zone).date()
        day_counts[local_day] += 1
        day_hours[local_day] += plan_events.hours_between(e.start, e.end)

    for exercise in auto_ex:
        duration = exercise.end - exercise.start
        if duration.total_seconds() <= 0:
            continue
        dur_h = plan_events.hours_between(exercise.start, exercise.end)
        activity = exercise.activity or models.Activity.CYCLING
        local_day = plan_events.as_local(exercise.start, zone).date()
        window = _exercise_window_for_activity(local_day, activity, ex, zone)
        fits_here = False
        if window is not None:
            day_start, day_end = window
            fits_here = (
                exercise.start >= day_start
                and exercise.end <= day_end
                and not plan_events.timed_events_overlap_slot(
                    placed, exercise.start, exercise.end
                )
                and day_counts[local_day] < max_blocks
                and day_hours[local_day] + dur_h <= max_hours + 1e-9
            )
        if fits_here:
            placed.append(exercise)
            day_counts[local_day] += 1
            day_hours[local_day] += dur_h
            continue

        new_slot = None
        for day in _candidate_exercise_days(
            week_start, week_end, zone, now
        ):
            if day_counts[day] >= max_blocks:
                continue
            if day_hours[day] + dur_h > max_hours + 1e-9:
                continue
            slot = _try_place_exercise(
                day, dur_h, placed, now, activity, ex, zone
            )
            if slot is not None:
                new_slot = (day, slot)
                break
        if new_slot is None:
            continue
        day, (start, end) = new_slot
        placed.append(
            exercise.model_copy(
                update={"start": start, "end": end, "conflict": False}
            )
        )
        day_counts[day] += 1
        day_hours[day] += dur_h

    state.events = placed
    return state


def _activity_counts_in_week(
    event_list: list[models.Event],
    week_start: datetime,
    week_end: datetime,
) -> dict[models.Activity, int]:
    counts: dict[models.Activity, int] = {
        models.Activity.CYCLING: 0,
        models.Activity.GYM: 0,
    }
    for e in event_list:
        if e.type != models.EventType.EXERCISE or e.activity is None:
            continue
        if plan_events.overlaps(e.start, e.end, week_start, week_end):
            counts[e.activity] = counts.get(e.activity, 0) + 1
    return counts


def _diverse_activity_order(
    counts: dict[models.Activity, int],
    local_day: date,
) -> list[models.Activity]:
    candidates = [models.Activity.GYM, models.Activity.CYCLING]
    rotation = [models.Activity.CYCLING, models.Activity.GYM]
    offset = local_day.toordinal() % len(rotation)
    rotated = rotation[offset:] + rotation[:offset]
    rank = {a: i for i, a in enumerate(rotated)}

    def sort_key(activity: models.Activity) -> tuple[int, int, int]:
        weekend_penalty = (
            1
            if local_day.weekday() >= 5 and activity == models.Activity.GYM
            else 0
        )
        return (
            counts.get(activity, 0),
            weekend_penalty,
            rank.get(activity, 99),
        )

    return sorted(candidates, key=sort_key)


def _day_has_exercise_room(
    event_list: list[models.Event],
    local_day: date,
    zone: ZoneInfo | timezone,
    session_min: float,
    max_blocks: int,
    max_hours: float,
) -> bool:
    if _exercise_count_on_date(event_list, local_day, zone) >= max_blocks:
        return False
    room = max_hours - _exercise_hours_on_date(event_list, local_day, zone)
    return room >= session_min - 1e-9


def _target_session_hours(
    remaining: float,
    room: float,
    session_min: float,
    session_max: float,
    open_days: int,
) -> float:
    if open_days <= 0:
        return min(session_max, room, remaining)
    even = remaining / open_days
    duration = min(session_max, room, max(session_min, even))
    if remaining - duration < session_min - 1e-9 and remaining <= room + 1e-9:
        if remaining >= session_min - 1e-9:
            duration = min(session_max, room, remaining)
    return duration


def _try_place_with_shop_slide(
    state: models.AppState,
    local_day: date,
    duration: float,
    now: datetime,
    act: models.Activity,
    ex: dict[str, Any],
    zone: ZoneInfo | timezone,
) -> tuple[datetime, datetime] | None:
    """Place exercise; slide Auto shopping same day only if needed."""
    slot = _try_place_exercise(
        local_day, duration, state.events, now, act, ex, zone
    )
    if slot is not None:
        return slot
    from app.services.plan import shopping as plan_shopping

    shop_events = [
        e
        for e in state.events
        if e.type == models.EventType.SHOPPING
        and e.origin == models.Origin.AUTO
        and plan_events.as_local(e.start, zone).date() == local_day
    ]
    if not shop_events:
        return None
    without_shop = [
        e for e in state.events if e.id not in {s.id for s in shop_events}
    ]
    slot = _try_place_exercise(
        local_day, duration, without_shop, now, act, ex, zone
    )
    if slot is None:
        return None
    new_events = list(without_shop)
    phantom = models.Event(
        title="_ex",
        type=models.EventType.EXERCISE,
        start=slot[0],
        end=slot[1],
        origin=models.Origin.AUTO,
    )
    for shop in shop_events:
        if not plan_events.overlaps(shop.start, shop.end, slot[0], slot[1]):
            new_events.append(shop)
            continue
        slid = plan_shopping.slide_trip_same_day(
            shop, new_events + [phantom], zone
        )
        if slid is None:
            return None
        new_events.append(slid)
    state.events = new_events
    return slot


def _place_one_exercise_session(
    state: models.AppState,
    local_day: date,
    duration: float,
    now: datetime,
    ex: dict[str, Any],
    zone: ZoneInfo | timezone,
    session_min: float,
    activity_counts: dict[models.Activity, int],
    *,
    allow_shop_slide: bool = False,
) -> tuple[float, models.Activity] | None:
    room = (
        plan_params.as_float(ex, "max_exercise_hours_per_day", 3.0)
        - _exercise_hours_on_date(state.events, local_day, zone)
    )
    if duration > room + 1e-9:
        duration = room
    if duration < session_min - 1e-9:
        return None

    for act in _diverse_activity_order(activity_counts, local_day):
        if allow_shop_slide:
            slot = _try_place_with_shop_slide(
                state, local_day, duration, now, act, ex, zone
            )
        else:
            slot = _try_place_exercise(
                local_day, duration, state.events, now, act, ex, zone
            )
        placed_dur = duration
        if slot is None and duration > session_min + 1e-9:
            shorter = min(session_min, room)
            if shorter >= session_min - 1e-9:
                if allow_shop_slide:
                    slot = _try_place_with_shop_slide(
                        state, local_day, shorter, now, act, ex, zone
                    )
                else:
                    slot = _try_place_exercise(
                        local_day, shorter, state.events, now, act, ex, zone
                    )
                if slot is not None:
                    placed_dur = shorter
        if slot is None:
            continue
        w_start, slot_end = slot
        state.events.append(
            models.Event(
                title=act.value.title(),
                type=models.EventType.EXERCISE,
                start=w_start,
                end=slot_end,
                origin=models.Origin.AUTO,
                activity=act,
            )
        )
        return placed_dur, act
    return None


def _fill_remaining(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
    *,
    clear_auto: bool,
    allow_shop_slide: bool,
) -> models.AppState:
    state = state.model_copy(deep=True)
    zone = plan_events.tz(state)
    if clear_auto:
        state.events = [
            e
            for e in state.events
            if not (
                e.type == models.EventType.EXERCISE
                and e.origin == models.Origin.AUTO
                and e.start < week_end
                and e.end > week_start
            )
        ]
    if not rules_access.rule_enabled(
        state, models.RuleKey.WEEKLY_EXERCISE_GOAL
    ):
        return state

    ex = rules_access.rule_params(state, models.RuleKey.WEEKLY_EXERCISE_GOAL)
    session_min = plan_params.as_float(ex, "session_min_hours", 1.0)
    session_max = plan_params.as_float(ex, "session_max_hours", 3.0)
    max_blocks = plan_params.as_int(ex, "max_exercise_blocks_per_day", 1)
    max_hours = plan_params.as_float(ex, "max_exercise_hours_per_day", 3.0)
    weekend_min = plan_params.as_float(ex, "weekend_min_hours", 4.0)

    week_summary = plan_summary.compute_week_summary(
        state, now, week_start, week_end
    )
    remaining = week_summary.remaining_hours
    activity_counts = _activity_counts_in_week(
        state.events, week_start, week_end
    )
    candidates = _candidate_exercise_days(week_start, week_end, zone, now)
    weekend_days = [d for d in candidates if d.weekday() >= 5]
    weekend_hours = sum(
        _exercise_hours_on_date(state.events, d, zone) for d in weekend_days
    )

    def _open_days(pool: list[date]) -> list[date]:
        return [
            d
            for d in pool
            if _day_has_exercise_room(
                state.events, d, zone, session_min, max_blocks, max_hours
            )
        ]

    def _place_on_day(
        local_day: date, want: float, *, open_pool: list[date] | None = None
    ) -> bool:
        nonlocal remaining, weekend_hours
        if remaining < session_min - 1e-9:
            return False
        if not _day_has_exercise_room(
            state.events, local_day, zone, session_min, max_blocks, max_hours
        ):
            return False
        hours_today = _exercise_hours_on_date(state.events, local_day, zone)
        room = max_hours - hours_today
        pool = open_pool if open_pool is not None else candidates
        open_n = len(_open_days(pool))
        duration = _target_session_hours(
            min(want, remaining),
            room,
            session_min,
            session_max,
            max(1, open_n),
        )
        placed = _place_one_exercise_session(
            state,
            local_day,
            duration,
            now,
            ex,
            zone,
            session_min,
            activity_counts,
            allow_shop_slide=allow_shop_slide,
        )
        if placed is None:
            return False
        placed_h, act = placed
        remaining = max(0.0, remaining - placed_h)
        activity_counts[act] = activity_counts.get(act, 0) + 1
        if local_day.weekday() >= 5:
            weekend_hours += placed_h
        return True

    weekend_need = max(0.0, weekend_min - weekend_hours)
    while weekend_need >= session_min - 1e-9 and remaining >= session_min - 1e-9:
        open_weekend = sorted(
            _open_days(weekend_days),
            key=lambda d: (
                _exercise_hours_on_date(state.events, d, zone),
                d.toordinal(),
            ),
        )
        if not open_weekend:
            break
        before = weekend_hours
        if not _place_on_day(
            open_weekend[0],
            min(weekend_need, remaining),
            open_pool=open_weekend,
        ):
            weekend_days = [d for d in weekend_days if d != open_weekend[0]]
            continue
        weekend_need = max(0.0, weekend_min - weekend_hours)
        if weekend_hours <= before + 1e-9:
            break

    while remaining >= session_min - 1e-9:
        open_all = sorted(
            _open_days(candidates),
            key=lambda d: (
                _exercise_count_on_date(state.events, d, zone),
                _exercise_hours_on_date(state.events, d, zone),
                d.toordinal(),
            ),
        )
        if not open_all:
            break
        if not _place_on_day(open_all[0], remaining, open_pool=open_all):
            candidates = [d for d in candidates if d != open_all[0]]
            continue

    return state


def place(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Clear Auto exercise in the week and fill toward the weekly goal."""
    return _fill_remaining(
        state,
        now,
        week_start,
        week_end,
        clear_auto=True,
        allow_shop_slide=False,
    )


def recover(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Place only unmet exercise hours; may slide Auto shopping same day."""
    return _fill_remaining(
        state,
        now,
        week_start,
        week_end,
        clear_auto=False,
        allow_shop_slide=True,
    )
