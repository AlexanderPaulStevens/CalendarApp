"""Deterministic plan recalculation engine."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.config import settings as app_config
from app.ingredients.shelf_life import ensure_fridge_shelf_lives
from app.rules.access import rule_enabled, rule_params
from app.rules.catalog import study_blocks_from_params, work_blocks_from_params
from app.schemas.models import (
    Activity,
    AppState,
    Event,
    EventType,
    Origin,
    PlanSnapshot,
    RuleKey,
    ShoppingLine,
    Unit,
    WeekSummary,
    new_id,
)
from app.signals import emit as signal_emit

ROUTINE_WORK_TITLE = "Work"
ROUTINE_STUDY_TITLE = "Study"
# How many extra weeks after the viewed week to plan (preload).
PLAN_PRELOAD_WEEKS = 1


def _tz(_state: AppState | None = None) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(app_config.default_timezone)
    except Exception:
        return timezone.utc


def _as_local(dt: datetime, tz: ZoneInfo | timezone) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _f(params: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = params.get(key, default)
    if val is None:
        return default
    return float(val)


def _i(params: dict[str, Any], key: str, default: int = 0) -> int:
    val = params.get(key, default)
    if val is None:
        return default
    return int(val)


def week_bounds(
    ref: datetime, tz: ZoneInfo | timezone
) -> tuple[datetime, datetime]:
    local = _as_local(ref, tz)
    monday_date = local.date() - timedelta(days=local.weekday())
    start = datetime(
        monday_date.year, monday_date.month, monday_date.day, tzinfo=tz
    )
    end = start + timedelta(days=7)
    return start, end


def planning_horizon(
    now: datetime,
    tz: ZoneInfo | timezone,
    weeks: int | None = None,
    through: date | None = None,
    *,
    preload_weeks: int = PLAN_PRELOAD_WEEKS,
) -> tuple[datetime, datetime]:
    """Range to (re)plan: week containing ``through`` (or today) + preload.

    Past weeks before the current Monday are not replanned. Auto events
    outside this window are left as persisted.
    """
    current_monday, _ = week_bounds(now, tz)
    if through is None:
        through = _as_local(now, tz).date()
    monday = through - timedelta(days=through.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=tz)
    if start < current_monday:
        start = current_monday
    # ``weeks`` kept for callers; default is viewed week only (+ preload).
    span = max(1, weeks if weeks is not None else 1)
    end = start + timedelta(days=7 * (span + max(0, preload_weeks)))
    return start, end


def iter_planning_weeks(
    now: datetime,
    tz: ZoneInfo | timezone,
    weeks: int | None = None,
    through: date | None = None,
    *,
    preload_weeks: int = PLAN_PRELOAD_WEEKS,
) -> list[tuple[datetime, datetime]]:
    start, end = planning_horizon(
        now, tz, weeks, through, preload_weeks=preload_weeks
    )
    out: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        out.append((cur, cur + timedelta(days=7)))
        cur += timedelta(days=7)
    return out


def event_window_for_week(
    state: AppState,
    anchor: date | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Monday–Sunday window containing anchor (or today when unset)."""
    tz = _tz(state)
    if anchor is None:
        anchor = _as_local(now, tz).date()
    monday = anchor - timedelta(days=anchor.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=tz)
    return start, start + timedelta(days=7)


def hours_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600.0)


def overlaps(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    return a_start < b_end and b_start < a_end


def mark_conflicts(events: list[Event]) -> list[Event]:
    """Set ``conflict`` on timed events that overlap another timed event.

    Avoids deep-copying the whole list; only copies events whose flag changes.
    """
    flags = [False] * len(events)
    timed_idx = [i for i, e in enumerate(events) if not e.all_day]
    for a, i in enumerate(timed_idx):
        ei = events[i]
        for j in timed_idx[a + 1 :]:
            ej = events[j]
            if overlaps(ei.start, ei.end, ej.start, ej.end):
                flags[i] = True
                flags[j] = True
    out: list[Event] = []
    for i, e in enumerate(events):
        if e.conflict == flags[i]:
            out.append(e)
        else:
            out.append(e.model_copy(update={"conflict": flags[i]}))
    return out


def available_qty(item, today: date) -> float:
    if item.expiration_date is not None and item.expiration_date < today:
        return 0.0
    return max(0.0, item.quantity)


def purchase_quantity(
    required: float,
    available: float,
    minimum: float,
    replenish: float,
) -> float:
    shortfall = max(0.0, required - available)
    projected = available - required + shortfall
    qty = shortfall
    if projected <= minimum and replenish > 0:
        qty = max(shortfall, replenish)
    return qty


def _consume_stock_for_uses(
    uses: list[tuple[date, float]],
    stock: float,
    expiration: date | None,
) -> list[tuple[date, float]]:
    """Subtract fridge stock from meal uses; return uncovered (day, qty) rows."""
    remaining: list[tuple[date, float]] = []
    on_hand = max(0.0, stock)
    for day, qty in uses:
        if expiration is not None and expiration < day:
            on_hand = 0.0
        if on_hand >= qty:
            on_hand -= qty
            continue
        need = qty - on_hand
        on_hand = 0.0
        remaining.append((day, need))
    return remaining


def free_windows_for_day(
    day_start: datetime,
    day_end: datetime,
    events: list[Event],
    min_hours: float,
) -> list[tuple[datetime, datetime]]:
    blocking = sorted(
        [
            e
            for e in events
            if not e.all_day and overlaps(e.start, e.end, day_start, day_end)
        ],
        key=lambda e: e.start,
    )
    windows: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for e in blocking:
        start = max(cursor, day_start)
        end = min(e.start, day_end)
        if hours_between(start, end) >= min_hours - 1e-9:
            windows.append((start, end))
        cursor = max(cursor, e.end)
    if hours_between(cursor, day_end) >= min_hours - 1e-9:
        windows.append((cursor, day_end))
    return windows


def _timed_events_overlap_slot(
    events: list[Event], start: datetime, end: datetime
) -> bool:
    for e in events:
        if e.all_day:
            continue
        if overlaps(e.start, e.end, start, end):
            return True
    return False


def find_non_overlapping_slot(
    preferred_start: datetime,
    duration: timedelta,
    events: list[Event],
    search_start: datetime,
    search_end: datetime,
) -> tuple[datetime, datetime] | None:
    preferred_end = preferred_start + duration
    if (
        preferred_start >= search_start
        and preferred_end <= search_end
        and not _timed_events_overlap_slot(
            events, preferred_start, preferred_end
        )
    ):
        return preferred_start, preferred_end

    min_hours = duration.total_seconds() / 3600.0
    for w_start, w_end in free_windows_for_day(
        search_start, search_end, events, min_hours
    ):
        if w_start <= preferred_start and preferred_start + duration <= w_end:
            return preferred_start, preferred_start + duration
        slot_end = w_start + duration
        if slot_end <= w_end:
            return w_start, slot_end
    return None


def compute_week_summary(
    state: AppState,
    now: datetime,
    week_start: datetime | None = None,
    week_end: datetime | None = None,
) -> WeekSummary:
    tz = _tz(state)
    if week_start is None or week_end is None:
        week_start, week_end = week_bounds(now, tz)
    ex = rule_params(state, RuleKey.WEEKLY_EXERCISE_GOAL)
    goal = _f(ex, "goal_hours", 10.0)
    session_min = _f(ex, "session_min_hours", 1.0)
    session_max = _f(ex, "session_max_hours", 3.0)
    max_hours = _f(ex, "max_exercise_hours_per_day", 3.0)

    completed = 0.0
    planned = 0.0
    exercise_events = [
        e
        for e in state.events
        if e.type == EventType.EXERCISE
        and e.start < week_end
        and e.end > week_start
    ]
    for e in exercise_events:
        h = hours_between(max(e.start, week_start), min(e.end, week_end))
        if e.completed or e.end <= now:
            completed += h
        else:
            planned += h

    remaining = max(0.0, goal - completed - planned)

    feasible_days = 0
    max_possible = 0.0
    day = max(_as_local(now, tz), week_start)
    while day < week_end:
        local_day = _as_local(day, tz).date()
        day_start = datetime(
            local_day.year, local_day.month, local_day.day, 6, 0, tzinfo=tz
        )
        day_end = datetime(
            local_day.year, local_day.month, local_day.day, 22, 0, tzinfo=tz
        )
        if day_end <= now:
            day = day_start + timedelta(days=1)
            continue
        window_start = max(day_start, now)
        windows = free_windows_for_day(
            window_start, day_end, state.events, session_min
        )
        day_capacity = 0.0
        for w_start, w_end in windows:
            day_capacity += min(session_max, hours_between(w_start, w_end))
        day_capacity = min(day_capacity, max_hours)
        if day_capacity >= session_min:
            feasible_days += 1
            max_possible += day_capacity
        day = day_start + timedelta(days=1)

    if remaining <= 0:
        sessions_needed = 0
    else:
        sessions_needed = int(math.ceil(remaining / session_max))

    return WeekSummary(
        completed_hours=round(completed, 2),
        planned_hours=round(planned, 2),
        remaining_hours=round(remaining, 2),
        sessions_needed=sessions_needed,
        feasible_days=feasible_days,
        feasible=remaining <= max_possible + 1e-6,
        max_possible_hours=round(max_possible, 2),
        goal_hours=goal,
    )


def _exercise_hours_before(
    state: AppState,
    local_date: date,
    before: datetime,
    tz: ZoneInfo | timezone,
) -> tuple[float, float]:
    """Return (total exercise hours, cycling hours) on local_date before ``before``."""
    total = 0.0
    cycling = 0.0
    for e in state.events:
        if e.type != EventType.EXERCISE:
            continue
        if _as_local(e.start, tz).date() != local_date:
            continue
        if e.end > before:
            continue
        h = hours_between(e.start, e.end)
        total += h
        if e.activity == Activity.CYCLING:
            cycling += h
    return total, cycling


def _pick_recipe(
    state: AppState,
    meal_type: str,
    *,
    slot_key: str = "",
    used_ids: set[str] | None = None,
    allow_repeat: bool = False,
    prefer_protein: bool = False,
    prefer_carb_protein: bool = False,
) -> str | None:
    """Pick a recipe for a meal slot.

    Selection is random but stable for ``slot_key`` so recalculation does
    not reshuffle the week. Lunch/dinner never reuse a recipe already
    placed this week; breakfast may repeat. After exercise, narrows to
    top protein/carb candidates among the remaining pool.
    """
    typed = [r for r in state.recipes if r.meal_type.lower() == meal_type]
    pool = typed or list(state.recipes)
    if not pool:
        return None
    used = used_ids or set()
    fresh = [r for r in pool if r.id not in used]
    if fresh:
        pool = fresh
    elif not allow_repeat:
        return None
    if prefer_carb_protein:
        pool = sorted(
            pool,
            key=lambda r: (r.carbohydrates_g + r.protein_g, r.protein_g),
            reverse=True,
        )
        pool = pool[: max(1, min(3, len(pool)))]
    elif prefer_protein:
        pool = sorted(pool, key=lambda r: r.protein_g, reverse=True)
        pool = pool[: max(1, min(3, len(pool)))]
    rng = random.Random(slot_key or meal_type)
    return rng.choice(pool).id


def _user_meal_covers_slot(
    events: list[Event],
    local_date: date,
    hour: int,
    tz: ZoneInfo | timezone,
) -> bool:
    for e in events:
        if e.type != EventType.MEAL or e.origin != Origin.USER:
            continue
        local = _as_local(e.start, tz)
        if local.date() == local_date and local.hour == hour:
            return True
    return False


def _user_work_on_day(
    events: list[Event], local_date: date, tz: ZoneInfo | timezone
) -> bool:
    for e in events:
        if e.origin != Origin.USER:
            continue
        if e.type == EventType.PERSONAL and e.title == ROUTINE_WORK_TITLE:
            if _as_local(e.start, tz).date() == local_date:
                return True
    return False


def _user_study_on_day(
    events: list[Event], local_date: date, tz: ZoneInfo | timezone
) -> bool:
    for e in events:
        if e.origin != Origin.USER:
            continue
        if e.type == EventType.PERSONAL and e.title == ROUTINE_STUDY_TITLE:
            if _as_local(e.start, tz).date() == local_date:
                return True
    return False


def _is_routine_event(e: Event) -> bool:
    if e.origin != Origin.AUTO:
        return False
    if e.type == EventType.PERSONAL and e.title in (
        ROUTINE_WORK_TITLE,
        ROUTINE_STUDY_TITLE,
    ):
        return True
    if e.type == EventType.MEAL:
        return True
    return False


def _lunch_break_bounds(
    local_date: date,
    meals: dict[str, Any],
    tz: ZoneInfo | timezone,
) -> tuple[datetime, datetime]:
    start = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        _i(meals, "lunch_hour", 12),
        0,
        tzinfo=tz,
    )
    end = start + timedelta(minutes=_i(meals, "lunch_duration_min", 60))
    return start, end


def _work_segments_around_lunch(
    block_start: datetime,
    block_end: datetime,
    lunch_start: datetime,
    lunch_end: datetime,
) -> list[tuple[datetime, datetime]]:
    if not overlaps(block_start, block_end, lunch_start, lunch_end):
        return [(block_start, block_end)] if block_start < block_end else []
    segments: list[tuple[datetime, datetime]] = []
    if block_start < lunch_start:
        segments.append((block_start, min(lunch_start, block_end)))
    if lunch_end < block_end:
        segments.append((max(lunch_end, block_start), block_end))
    return [(s, e) for s, e in segments if s < e]


def apply_work_and_meals(
    state: AppState, now: datetime, through: date | None = None
) -> AppState:
    """Upsert Auto work, study, and meal slots over the planning horizon."""
    tz = _tz(state)
    horizon_start, horizon_end = planning_horizon(now, tz, through=through)
    meals = rule_params(state, RuleKey.DAILY_MEALS)
    work = rule_params(state, RuleKey.WORK_SCHEDULE)
    study = rule_params(state, RuleKey.STUDY_SCHEDULE)
    ex = rule_params(state, RuleKey.WEEKLY_EXERCISE_GOAL)
    state = state.model_copy(deep=True)
    state.events = [
        e
        for e in state.events
        if not (
            _is_routine_event(e)
            and e.start < horizon_end
            and e.end > horizon_start
        )
    ]

    place_work = rule_enabled(state, RuleKey.WORK_SCHEDULE)
    place_study = rule_enabled(state, RuleKey.STUDY_SCHEDULE)
    place_meals = rule_enabled(state, RuleKey.DAILY_MEALS)
    if not place_work and not place_study and not place_meals:
        return state

    earliest = max(0, min(23, _i(ex, "exercise_earliest_hour", 7)))
    threshold = _f(meals, "activity_threshold_hours", 2.0)
    day = horizon_start
    while day < horizon_end:
        local_date = _as_local(day, tz).date()
        weekday = local_date.weekday()
        day_search_start = datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            earliest,
            0,
            tzinfo=tz,
        )
        day_search_end = datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            22,
            0,
            tzinfo=tz,
        )
        lunch_start, lunch_end = _lunch_break_bounds(local_date, meals, tz)

        if place_work and not _user_work_on_day(state.events, local_date, tz):
            for block in work_blocks_from_params(work):
                if block.weekday != weekday:
                    continue
                start_h = int(block.start_hour)
                start_m = int(round((block.start_hour - start_h) * 60))
                end_h = int(block.end_hour)
                end_m = int(round((block.end_hour - end_h) * 60))
                block_start = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    start_h,
                    start_m,
                    tzinfo=tz,
                )
                block_end = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    end_h,
                    end_m,
                    tzinfo=tz,
                )
                for seg_start, seg_end in _work_segments_around_lunch(
                    block_start, block_end, lunch_start, lunch_end
                ):
                    state.events.append(
                        Event(
                            title=ROUTINE_WORK_TITLE,
                            type=EventType.PERSONAL,
                            start=seg_start,
                            end=seg_end,
                            origin=Origin.AUTO,
                        )
                    )

        if place_study and not _user_study_on_day(
            state.events, local_date, tz
        ):
            for block in study_blocks_from_params(study):
                if block.weekday != weekday:
                    continue
                start_h = int(block.start_hour)
                start_m = int(round((block.start_hour - start_h) * 60))
                end_h = int(block.end_hour)
                end_m = int(round((block.end_hour - end_h) * 60))
                block_start = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    start_h,
                    start_m,
                    tzinfo=tz,
                )
                block_end = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    end_h,
                    end_m,
                    tzinfo=tz,
                )
                if block_start >= block_end:
                    continue
                state.events.append(
                    Event(
                        title=ROUTINE_STUDY_TITLE,
                        type=EventType.PERSONAL,
                        start=block_start,
                        end=block_end,
                        origin=Origin.AUTO,
                    )
                )

        if place_meals:
            meal_slots = [
                (
                    "Breakfast",
                    _i(meals, "breakfast_hour", 8),
                    "breakfast",
                    _i(meals, "meal_duration_min", 45),
                ),
                (
                    "Lunch",
                    _i(meals, "lunch_hour", 12),
                    "lunch",
                    _i(meals, "lunch_duration_min", 60),
                ),
                (
                    "Dinner",
                    _i(meals, "dinner_hour", 18),
                    "dinner",
                    _i(meals, "meal_duration_min", 45),
                ),
            ]
            # Uniqueness is per calendar week: lunch/dinner never repeat
            # within Mon–Sun; breakfast may. Scope to this week only so
            # the planning horizon can reuse recipes in later weeks.
            week_monday = local_date - timedelta(days=weekday)
            week_end_date = week_monday + timedelta(days=7)
            used_recipe_ids = {
                e.recipe_id
                for e in state.events
                if e.type == EventType.MEAL
                and e.recipe_id
                and week_monday
                <= _as_local(e.start, tz).date()
                < week_end_date
            }
            for title, hour, meal_type, duration_min in meal_slots:
                if _user_meal_covers_slot(state.events, local_date, hour, tz):
                    continue
                preferred = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    hour,
                    0,
                    tzinfo=tz,
                )
                ex_h, cyc_h = _exercise_hours_before(
                    state, local_date, preferred, tz
                )
                prefer_carb = cyc_h >= threshold
                prefer_protein = ex_h >= threshold
                allow_repeat = meal_type == "breakfast"
                slot_key = f"{local_date.isoformat()}:{meal_type}"
                recipe_id = _pick_recipe(
                    state,
                    meal_type,
                    slot_key=slot_key,
                    used_ids=used_recipe_ids,
                    allow_repeat=allow_repeat,
                    prefer_protein=prefer_protein and not prefer_carb,
                    prefer_carb_protein=prefer_carb,
                )
                if not recipe_id and meal_type == "lunch":
                    recipe_id = _pick_recipe(
                        state,
                        "dinner",
                        slot_key=f"{slot_key}:fallback",
                        used_ids=used_recipe_ids,
                        allow_repeat=False,
                        prefer_protein=prefer_protein and not prefer_carb,
                        prefer_carb_protein=prefer_carb,
                    )
                if not recipe_id:
                    continue
                recipe = next(
                    (r for r in state.recipes if r.id == recipe_id), None
                )
                slot = find_non_overlapping_slot(
                    preferred,
                    timedelta(minutes=duration_min),
                    state.events,
                    day_search_start,
                    day_search_end,
                )
                if slot is None:
                    continue
                start, end = slot
                used_recipe_ids.add(recipe_id)
                state.events.append(
                    Event(
                        title=recipe.name if recipe else title,
                        type=EventType.MEAL,
                        start=start,
                        end=end,
                        origin=Origin.AUTO,
                        recipe_id=recipe_id,
                        portions=1.0,
                    )
                )

        day = day + timedelta(days=1)

    return state


def _exercise_count_on_date(
    events: list[Event], day: date, tz: ZoneInfo | timezone
) -> int:
    return sum(
        1
        for e in events
        if e.type == EventType.EXERCISE
        and _as_local(e.start, tz).date() == day
    )


def _exercise_hours_on_date(
    events: list[Event], day: date, tz: ZoneInfo | timezone
) -> float:
    return sum(
        hours_between(e.start, e.end)
        for e in events
        if e.type == EventType.EXERCISE
        and _as_local(e.start, tz).date() == day
    )


def _no_morning_weekdays(ex: dict[str, Any]) -> set[int]:
    raw = ex.get("no_morning_weekdays")
    if not isinstance(raw, list):
        raw = [0, 3]
    return {int(x) for x in raw}


def _exercise_window_for_activity(
    local_day: date,
    activity: Activity,
    ex: dict[str, Any],
    tz: ZoneInfo | timezone,
) -> tuple[datetime, datetime] | None:
    """Allowed search window for Auto exercise of ``activity`` on ``local_day``."""
    earliest = max(0, min(23, _i(ex, "exercise_earliest_hour", 7)))
    morning_end = max(
        earliest + 1, min(23, _i(ex, "morning_end_hour", 12))
    )
    cycling_latest = max(
        morning_end, min(24, _i(ex, "cycling_latest_end_hour", 20))
    )
    day_end_h = 22

    if activity == Activity.CYCLING:
        # Cycling is never morning; evening sessions must end by cycling_latest.
        start_h = morning_end
        end_h = min(day_end_h, cycling_latest)
    else:
        # Gym: morning allowed except Mon/Thu; may run through day end.
        if local_day.weekday() in _no_morning_weekdays(ex):
            start_h = morning_end
        else:
            start_h = earliest
        end_h = day_end_h

    if end_h <= start_h:
        return None
    return (
        datetime(
            local_day.year,
            local_day.month,
            local_day.day,
            start_h,
            0,
            tzinfo=tz,
        ),
        datetime(
            local_day.year,
            local_day.month,
            local_day.day,
            end_h,
            0,
            tzinfo=tz,
        ),
    )


def _preferred_exercise_start(
    local_day: date,
    activity: Activity,
    window_start: datetime,
    floor: datetime,
    ex: dict[str, Any],
    tz: ZoneInfo | timezone,
) -> datetime:
    earliest = max(0, min(23, _i(ex, "exercise_earliest_hour", 7)))
    morning_end = max(
        earliest + 1, min(23, _i(ex, "morning_end_hour", 12))
    )
    evening_start = max(
        morning_end, min(22, _i(ex, "evening_start_hour", 17))
    )
    # Weekends: morning gym when allowed; otherwise afternoon.
    # Weekdays: prefer evening.
    if local_day.weekday() >= 5 and activity == Activity.GYM:
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
        tzinfo=tz,
    )
    return max(floor, window_start, preferred)


def _try_place_exercise(
    local_day: date,
    duration_h: float,
    events: list[Event],
    now: datetime,
    activity: Activity,
    ex: dict[str, Any],
    tz: ZoneInfo | timezone,
) -> tuple[datetime, datetime] | None:
    window = _exercise_window_for_activity(local_day, activity, ex, tz)
    if window is None:
        return None
    ds, de = window
    if de <= now:
        return None
    floor = max(ds, now) if local_day == _as_local(now, tz).date() else ds
    if floor >= de:
        return None
    preferred = _preferred_exercise_start(
        local_day, activity, ds, floor, ex, tz
    )
    if preferred >= de:
        preferred = floor
    return find_non_overlapping_slot(
        preferred, timedelta(hours=duration_h), events, floor, de
    )


def _dedupe_identical_events(events: list[Event]) -> list[Event]:
    seen: set[tuple] = set()
    out: list[Event] = []
    for e in events:
        key = (
            e.type,
            e.start.isoformat(),
            e.end.isoformat(),
            e.title,
            e.recipe_id,
            e.activity,
            e.origin,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _candidate_exercise_days(
    week_start: datetime,
    week_end: datetime,
    tz: ZoneInfo | timezone,
    now: datetime,
) -> list[date]:
    """Remaining days this week from today, chronological (one session/day)."""
    days: list[date] = []
    d = _as_local(week_start, tz).date()
    end = _as_local(week_end - timedelta(seconds=1), tz).date()
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    today = _as_local(now, tz).date()
    return [x for x in days if x >= today]


def repair_exercise_events(
    state: AppState, now: datetime, through: date | None = None
) -> AppState:
    """Move Auto exercise out of conflicts; never move User exercise."""
    tz = _tz(state)
    ex = rule_params(state, RuleKey.WEEKLY_EXERCISE_GOAL)
    max_blocks = _i(ex, "max_exercise_blocks_per_day", 1)
    max_hours = _f(ex, "max_exercise_hours_per_day", 3.0)
    horizon_start, horizon_end = planning_horizon(now, tz, through=through)
    state = state.model_copy(deep=True)

    user_ex = [
        e
        for e in state.events
        if e.type == EventType.EXERCISE and e.origin != Origin.AUTO
    ]
    auto_ex = sorted(
        [
            e
            for e in state.events
            if e.type == EventType.EXERCISE and e.origin == Origin.AUTO
        ],
        key=lambda e: (e.start, e.id),
    )
    others = [e for e in state.events if e.type != EventType.EXERCISE]
    placed: list[Event] = list(others) + list(user_ex)
    day_counts: dict[date, int] = defaultdict(int)
    day_hours: dict[date, float] = defaultdict(float)
    for e in user_ex:
        local_day = _as_local(e.start, tz).date()
        day_counts[local_day] += 1
        day_hours[local_day] += hours_between(e.start, e.end)

    for exercise in auto_ex:
        duration = exercise.end - exercise.start
        if duration.total_seconds() <= 0:
            continue
        dur_h = hours_between(exercise.start, exercise.end)
        activity = exercise.activity or Activity.CYCLING
        local = _as_local(exercise.start, tz)
        local_day = local.date()
        window = _exercise_window_for_activity(local_day, activity, ex, tz)
        fits_here = False
        if window is not None:
            day_start, day_end = window
            fits_here = (
                exercise.start >= day_start
                and exercise.end <= day_end
                and not _timed_events_overlap_slot(
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
            horizon_start, horizon_end, tz, now
        ):
            if day_counts[day] >= max_blocks:
                continue
            if day_hours[day] + dur_h > max_hours + 1e-9:
                continue
            slot = _try_place_exercise(
                day, dur_h, placed, now, activity, ex, tz
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
    events: list[Event],
    week_start: datetime,
    week_end: datetime,
) -> dict[Activity, int]:
    counts: dict[Activity, int] = {
        Activity.CYCLING: 0,
        Activity.GYM: 0,
    }
    for e in events:
        if e.type != EventType.EXERCISE or e.activity is None:
            continue
        if overlaps(e.start, e.end, week_start, week_end):
            counts[e.activity] = counts.get(e.activity, 0) + 1
    return counts


def _diverse_activity_order(
    counts: dict[Activity, int],
    local_day: date,
) -> list[Activity]:
    """Least-used activities first so the week rotates gym/cycling."""
    candidates = [Activity.GYM, Activity.CYCLING]

    # Rotate tie-break by day so the same activity is not always second pick.
    rotation = [Activity.CYCLING, Activity.GYM]
    offset = local_day.toordinal() % len(rotation)
    rotated = rotation[offset:] + rotation[:offset]
    rank = {a: i for i, a in enumerate(rotated)}

    def sort_key(activity: Activity) -> tuple[int, int, int]:
        # On weekends, prefer cycling so gym does not consume open days.
        weekend_penalty = (
            1 if local_day.weekday() >= 5 and activity == Activity.GYM else 0
        )
        return (counts.get(activity, 0), weekend_penalty, rank.get(activity, 99))

    return sorted(candidates, key=sort_key)


def _day_has_exercise_room(
    events: list[Event],
    local_day: date,
    tz: ZoneInfo | timezone,
    session_min: float,
    max_blocks: int,
    max_hours: float,
) -> bool:
    if _exercise_count_on_date(events, local_day, tz) >= max_blocks:
        return False
    room = max_hours - _exercise_hours_on_date(events, local_day, tz)
    return room >= session_min - 1e-9


def _target_session_hours(
    remaining: float,
    room: float,
    session_min: float,
    session_max: float,
    open_days: int,
) -> float:
    """Size a session so remaining hours can still cover open days."""
    if open_days <= 0:
        return min(session_max, room, remaining)
    even = remaining / open_days
    duration = min(session_max, room, max(session_min, even))
    if remaining - duration < session_min - 1e-9 and remaining <= room + 1e-9:
        # Last chunk: take what's left if it still fits session bounds.
        if remaining >= session_min - 1e-9:
            duration = min(session_max, room, remaining)
    return duration


def _place_one_exercise_session(
    state: AppState,
    local_day: date,
    duration: float,
    now: datetime,
    ex: dict[str, Any],
    tz: ZoneInfo | timezone,
    session_min: float,
    activity_counts: dict[Activity, int],
) -> tuple[float, Activity] | None:
    """Try to place one Auto session; return (hours, activity) or None."""
    room = (
        _f(ex, "max_exercise_hours_per_day", 3.0)
        - _exercise_hours_on_date(state.events, local_day, tz)
    )
    if duration > room + 1e-9:
        duration = room
    if duration < session_min - 1e-9:
        return None

    for act in _diverse_activity_order(activity_counts, local_day):
        slot = _try_place_exercise(
            local_day, duration, state.events, now, act, ex, tz
        )
        placed_dur = duration
        if slot is None and duration > session_min + 1e-9:
            shorter = min(session_min, room)
            if shorter >= session_min - 1e-9:
                slot = _try_place_exercise(
                    local_day, shorter, state.events, now, act, ex, tz
                )
                if slot is not None:
                    placed_dur = shorter
        if slot is None:
            continue
        w_start, slot_end = slot
        state.events.append(
            Event(
                title=act.value.title(),
                type=EventType.EXERCISE,
                start=w_start,
                end=slot_end,
                origin=Origin.AUTO,
                activity=act,
            )
        )
        return placed_dur, act
    return None


def place_auto_exercise(
    state: AppState, now: datetime, through: date | None = None
) -> AppState:
    """Fill toward each week's goal across the planning horizon.

    Spreads sessions over remaining days, rotates activities, and prefers
    meeting ``weekend_min_hours`` on Sat+Sun before packing weekdays.
    """
    state = state.model_copy(deep=True)
    tz = _tz(state)
    horizon_start, horizon_end = planning_horizon(now, tz, through=through)
    state.events = [
        e
        for e in state.events
        if not (
            e.type == EventType.EXERCISE
            and e.origin == Origin.AUTO
            and e.start < horizon_end
            and e.end > horizon_start
        )
    ]
    if not rule_enabled(state, RuleKey.WEEKLY_EXERCISE_GOAL):
        return state

    ex = rule_params(state, RuleKey.WEEKLY_EXERCISE_GOAL)
    session_min = _f(ex, "session_min_hours", 1.0)
    session_max = _f(ex, "session_max_hours", 3.0)
    max_blocks = _i(ex, "max_exercise_blocks_per_day", 1)
    max_hours = _f(ex, "max_exercise_hours_per_day", 3.0)
    weekend_min = _f(ex, "weekend_min_hours", 4.0)

    for week_start, week_end in iter_planning_weeks(now, tz, through=through):
        summary = compute_week_summary(state, now, week_start, week_end)
        remaining = summary.remaining_hours
        activity_counts = _activity_counts_in_week(
            state.events, week_start, week_end
        )
        candidates = _candidate_exercise_days(
            week_start, week_end, tz, now
        )
        weekend_days = [d for d in candidates if d.weekday() >= 5]
        weekend_hours = sum(
            _exercise_hours_on_date(state.events, d, tz) for d in weekend_days
        )

        def _open_days(pool: list[date]) -> list[date]:
            return [
                d
                for d in pool
                if _day_has_exercise_room(
                    state.events,
                    d,
                    tz,
                    session_min,
                    max_blocks,
                    max_hours,
                )
            ]

        def _place_on_day(
            local_day: date, want: float, *, open_pool: list[date] | None = None
        ) -> bool:
            nonlocal remaining, weekend_hours
            if remaining < session_min - 1e-9:
                return False
            if not _day_has_exercise_room(
                state.events,
                local_day,
                tz,
                session_min,
                max_blocks,
                max_hours,
            ):
                return False
            hours_today = _exercise_hours_on_date(
                state.events, local_day, tz
            )
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
                tz,
                session_min,
                activity_counts,
            )
            if placed is None:
                return False
            placed_h, act = placed
            remaining = max(0.0, remaining - placed_h)
            activity_counts[act] = activity_counts.get(act, 0) + 1
            if local_day.weekday() >= 5:
                weekend_hours += placed_h
            return True

        # Phase 1: prioritize weekend toward weekend_min_hours.
        weekend_need = max(0.0, weekend_min - weekend_hours)
        while weekend_need >= session_min - 1e-9 and remaining >= session_min - 1e-9:
            open_weekend = sorted(
                _open_days(weekend_days),
                key=lambda d: (
                    _exercise_hours_on_date(state.events, d, tz),
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
                # Skip a day that cannot fit any activity window.
                weekend_days = [
                    d for d in weekend_days if d != open_weekend[0]
                ]
                continue
            weekend_need = max(0.0, weekend_min - weekend_hours)
            if weekend_hours <= before + 1e-9:
                break

        # Phase 2: spread remaining hours across all days (fewest hours first).
        while remaining >= session_min - 1e-9:
            open_all = sorted(
                _open_days(candidates),
                key=lambda d: (
                    _exercise_count_on_date(state.events, d, tz),
                    _exercise_hours_on_date(state.events, d, tz),
                    d.toordinal(),
                ),
            )
            if not open_all:
                break
            if not _place_on_day(open_all[0], remaining, open_pool=open_all):
                candidates = [d for d in candidates if d != open_all[0]]
                continue

    return state


def _study_hours_on_date(
    events: list[Event], day: date, tz: ZoneInfo | timezone
) -> float:
    return sum(
        hours_between(e.start, e.end)
        for e in events
        if e.type == EventType.PERSONAL
        and e.title == ROUTINE_STUDY_TITLE
        and _as_local(e.start, tz).date() == day
    )


def place_weekend_study(
    state: AppState, now: datetime, through: date | None = None
) -> AppState:
    """Pack Auto study into Sat/Sun free time toward weekend_goal_hours.

    Hours are not fixed clocks — any free slot between earliest and latest
    is eligible. Runs after exercise so weekend exercise keeps priority.
    """
    if not rule_enabled(state, RuleKey.STUDY_SCHEDULE):
        return state

    state = state.model_copy(deep=True)
    tz = _tz(state)
    study = rule_params(state, RuleKey.STUDY_SCHEDULE)
    goal = _f(study, "weekend_goal_hours", 14.0)
    earliest = max(0, min(23, _i(study, "weekend_earliest_hour", 7)))
    latest = max(earliest + 1, min(24, _i(study, "weekend_latest_hour", 22)))
    block_min = _f(study, "weekend_block_min_hours", 2.0)
    block_max = _f(study, "weekend_block_max_hours", 4.0)
    today = _as_local(now, tz).date()

    for week_start, week_end in iter_planning_weeks(now, tz, through=through):
        monday = _as_local(week_start, tz).date()
        weekend_days = [
            d
            for d in (monday + timedelta(days=5), monday + timedelta(days=6))
            if d >= today and d < _as_local(week_end, tz).date()
        ]
        weekend_days = [
            d
            for d in weekend_days
            if not _user_study_on_day(state.events, d, tz)
        ]
        if not weekend_days:
            continue

        placed_hours = sum(
            _study_hours_on_date(state.events, d, tz) for d in weekend_days
        )
        remaining = max(0.0, goal - placed_hours)

        while remaining >= block_min - 1e-9:
            day = min(
                weekend_days,
                key=lambda d: (
                    _study_hours_on_date(state.events, d, tz),
                    d.toordinal(),
                ),
            )
            day_start = datetime(
                day.year, day.month, day.day, earliest, 0, tzinfo=tz
            )
            day_end = datetime(
                day.year, day.month, day.day, latest, 0, tzinfo=tz
            )
            if day == today:
                day_start = max(day_start, now)
            if day_start >= day_end:
                weekend_days = [d for d in weekend_days if d != day]
                if not weekend_days:
                    break
                continue

            open_n = len(weekend_days)
            even = remaining / max(1, open_n)
            target = min(block_max, remaining, max(block_min, even))
            if (
                remaining - target < block_min - 1e-9
                and remaining <= block_max + 1e-9
            ):
                target = min(block_max, remaining)

            windows = free_windows_for_day(
                day_start, day_end, state.events, block_min
            )
            if not windows:
                weekend_days = [d for d in weekend_days if d != day]
                if not weekend_days:
                    break
                continue

            # Pack the largest free window so study stays in fewer long blocks.
            w_start, w_end = max(
                windows, key=lambda w: hours_between(w[0], w[1])
            )
            fit = min(target, hours_between(w_start, w_end))
            if fit < block_min - 1e-9:
                weekend_days = [d for d in weekend_days if d != day]
                if not weekend_days:
                    break
                continue
            # Absorb leftover into this block when it would not form another.
            leftover = remaining - fit
            if (
                leftover < block_min - 1e-9
                and remaining <= hours_between(w_start, w_end) + 1e-9
                and remaining <= block_max + 1e-9
            ):
                fit = remaining

            slot = (w_start, w_start + timedelta(hours=fit))
            duration_h = fit

            s, e = slot
            state.events.append(
                Event(
                    title=ROUTINE_STUDY_TITLE,
                    type=EventType.PERSONAL,
                    start=s,
                    end=e,
                    origin=Origin.AUTO,
                )
            )
            remaining = max(0.0, remaining - duration_h)

    return state


def recompute_shopping(
    state: AppState, now: datetime
) -> tuple[list[ShoppingLine], list[Event]]:
    """Build shopping list and Auto store-trip events inside store hours."""
    tz = _tz(state)
    today = _as_local(now, tz).date()
    shop = rule_params(state, RuleKey.BATCH_SHOPPING)
    recipes = {r.id: r for r in state.recipes}
    inv_by_name = {i.name.lower(): i for i in state.fridge}

    meal_uses: dict[str, list[tuple[date, float]]] = defaultdict(list)
    demand_unit: dict[str, Unit] = {}
    display_name: dict[str, str] = {}

    for e in sorted(
        [ev for ev in state.events if ev.type == EventType.MEAL],
        key=lambda x: x.start,
    ):
        recipe = recipes.get(e.recipe_id or "")
        if not recipe:
            continue
        meal_day = _as_local(e.start, tz).date()
        for line in recipe.ingredients:
            key = line.name.lower()
            qty = line.quantity * e.portions
            meal_uses[key].append((meal_day, qty))
            demand_unit[key] = line.unit
            display_name[key] = line.name

    lead = max(0, _i(shop, "shopping_lead_days", 1))
    batch_days = max(1, _i(shop, "shopping_batch_days", 4))
    batch_on = rule_enabled(state, RuleKey.BATCH_SHOPPING)

    pending: list[tuple[date, str, float, Unit]] = []
    for key, uses in meal_uses.items():
        item = inv_by_name.get(key)
        available = available_qty(item, today) if item else 0.0
        expiration = item.expiration_date if item else None
        uncovered = _consume_stock_for_uses(uses, available, expiration)
        if not uncovered:
            continue
        name = display_name[key]
        unit = demand_unit.get(key, Unit.G)
        for day, qty in uncovered:
            need_day = day if day >= today else today
            pending.append((need_day, name, qty, unit))

    kept_events = [
        e
        for e in state.events
        if not (e.type == EventType.SHOPPING and e.origin == Origin.AUTO)
    ]
    if not batch_on:
        # No store-trip events — merged shortfall list (no trip_date).
        merged_flat: dict[str, tuple[float, Unit]] = {}
        order_flat: list[str] = []
        for _need, name, qty, unit in sorted(
            pending, key=lambda row: (row[0], row[1].lower())
        ):
            if name not in merged_flat:
                order_flat.append(name)
                merged_flat[name] = (qty, unit)
            else:
                prev_qty, prev_unit = merged_flat[name]
                merged_flat[name] = (prev_qty + qty, prev_unit)
        flat = [
            ShoppingLine(
                ingredient=name,
                quantity=merged_flat[name][0],
                unit=merged_flat[name][1],
            )
            for name in order_flat
        ]
        return flat, kept_events

    shop_duration = timedelta(
        minutes=max(15, _i(shop, "shopping_duration_min", 45))
    )
    open_h = max(0, min(23, _i(shop, "store_open_hour", 9)))
    close_h = max(open_h + 1, min(24, _i(shop, "store_close_hour", 19)))

    def _user_shopping_covering(trip_day: date) -> Event | None:
        """User store trip on trip_day or within the batch window."""
        best: Event | None = None
        best_delta: int | None = None
        for e in kept_events:
            if e.type != EventType.SHOPPING or e.origin == Origin.AUTO:
                continue
            ed = _as_local(e.start, tz).date()
            delta = (ed - trip_day).days
            if delta < 0 or delta >= batch_days:
                continue
            if best_delta is None or delta < best_delta:
                best = e
                best_delta = delta
        return best

    def _find_auto_slot(day: date) -> tuple[datetime, datetime] | None:
        preferred_hour = min(
            close_h - 1, max(open_h, 10 if day.weekday() >= 5 else 17)
        )
        preferred = datetime(
            day.year, day.month, day.day, preferred_hour, 0, tzinfo=tz
        )
        search_start = datetime(
            day.year, day.month, day.day, open_h, 0, tzinfo=tz
        )
        search_end = datetime(
            day.year, day.month, day.day, close_h, 0, tzinfo=tz
        )
        slot = find_non_overlapping_slot(
            preferred, shop_duration, kept_events, search_start, search_end
        )
        if slot is not None:
            return slot
        for offset in range(1, 8):
            alt = day + timedelta(days=offset)
            preferred = datetime(
                alt.year,
                alt.month,
                alt.day,
                min(
                    close_h - 1,
                    max(open_h, 10 if alt.weekday() >= 5 else 17),
                ),
                0,
                tzinfo=tz,
            )
            search_start = datetime(
                alt.year, alt.month, alt.day, open_h, 0, tzinfo=tz
            )
            search_end = datetime(
                alt.year, alt.month, alt.day, close_h, 0, tzinfo=tz
            )
            slot = find_non_overlapping_slot(
                preferred,
                shop_duration,
                kept_events,
                search_start,
                search_end,
            )
            if slot is not None:
                return slot
        return None

    def _rows_for_trip(
        rows: list[tuple[date, str, float, Unit]], trip_day: date
    ) -> tuple[
        list[tuple[date, str, float, Unit]],
        list[tuple[date, str, float, Unit]],
    ]:
        """Split rows into covered by trip_day vs leftover (batch + shelf)."""
        cover_until = trip_day + timedelta(days=batch_days)
        covered: list[tuple[date, str, float, Unit]] = []
        leftover: list[tuple[date, str, float, Unit]] = []
        for row in rows:
            need_day, name, qty, unit = row
            if need_day >= cover_until:
                leftover.append(row)
                continue
            item = inv_by_name.get(name.lower())
            shelf = item.shelf_life_days if item else None
            if shelf is not None and need_day > trip_day + timedelta(days=shelf):
                leftover.append(row)
                continue
            covered.append(row)
        return covered, leftover

    def _merge_trip_items(
        covered: list[tuple[date, str, float, Unit]],
    ) -> list[tuple[str, float, Unit]]:
        merged: dict[str, tuple[float, Unit]] = {}
        order: list[str] = []
        for _need, name, qty, unit in covered:
            if name not in merged:
                order.append(name)
                merged[name] = (qty, unit)
            else:
                prev_qty, prev_unit = merged[name]
                merged[name] = (prev_qty + qty, prev_unit)
        items: list[tuple[str, float, Unit]] = []
        for name in order:
            qty, unit = merged[name]
            item = inv_by_name.get(name.lower())
            shelf = item.shelf_life_days if item else None
            if shelf is None:
                minimum = item.minimum_quantity if item else 0.0
                replenish = item.replenishment_quantity if item else 0.0
                qty = purchase_quantity(qty, 0.0, minimum, replenish)
            items.append((name, qty, unit))
        return items

    trip_lines: list[ShoppingLine] = []
    remaining = sorted(pending, key=lambda row: (row[0], row[1].lower()))
    # Guard against a stuck row that can never be placed.
    stalled = 0
    while remaining and stalled < len(remaining) + 5:
        first_need = remaining[0][0]
        ideal_trip = first_need - timedelta(days=lead)
        if ideal_trip < today:
            ideal_trip = today

        user_trip = _user_shopping_covering(ideal_trip)
        if user_trip is not None:
            trip_date = _as_local(user_trip.start, tz).date()
            covered, leftover = _rows_for_trip(remaining, trip_date)
            if not covered:
                # User trip too early/late for this need — try Auto instead.
                user_trip = None
            else:
                items = _merge_trip_items(covered)
                for name, qty, unit in items:
                    trip_lines.append(
                        ShoppingLine(
                            ingredient=name,
                            quantity=qty,
                            unit=unit,
                            trip_date=trip_date,
                        )
                    )
                remaining = leftover
                stalled = 0
                continue

        slot = _find_auto_slot(ideal_trip)
        if slot is None:
            stalled += 1
            # Rotate the blocking row to the end so others can place.
            remaining = remaining[1:] + remaining[:1]
            continue
        start, end = slot
        trip_date = _as_local(start, tz).date()
        covered, leftover = _rows_for_trip(remaining, trip_date)
        if not covered:
            stalled += 1
            remaining = remaining[1:] + remaining[:1]
            continue
        items = _merge_trip_items(covered)
        parts = [f"{n} {q:g}{u.value}" for n, q, u in items]
        title = "Shopping — " + ", ".join(parts)
        if len(title) > 80:
            title = f"Shopping — {len(items)} items"
        kept_events.append(
            Event(
                id=new_id(),
                title=title,
                type=EventType.SHOPPING,
                start=start,
                end=end,
                all_day=False,
                origin=Origin.AUTO,
                ingredient_name=items[0][0] if len(items) == 1 else None,
            )
        )
        for name, qty, unit in items:
            trip_lines.append(
                ShoppingLine(
                    ingredient=name,
                    quantity=qty,
                    unit=unit,
                    trip_date=trip_date,
                )
            )
        remaining = leftover
        stalled = 0

    return trip_lines, kept_events


def recalculate(
    state: AppState,
    now: datetime | None = None,
    through: date | None = None,
) -> AppState:
    """Replan Auto events for the week of ``through`` (or today) + preload.

    Auto events outside that window are left as already persisted. Past
    weeks before the current Monday are not rewritten. Conflict flags are
    left unchanged here — callers mark conflicts on the events they return.
    """
    now = now or datetime.now(timezone.utc)
    state = state.model_copy(deep=True)
    state = ensure_fridge_shelf_lives(state)
    state.events = _dedupe_identical_events(state.events)
    state = apply_work_and_meals(state, now, through)
    state = repair_exercise_events(state, now, through)
    state = place_auto_exercise(state, now, through)

    shopping, events_after_shopping = recompute_shopping(state, now)
    state.events = events_after_shopping
    horizon_start, horizon_end = planning_horizon(
        now, _tz(state), through=through
    )
    state.events = [
        e
        for e in state.events
        if not (
            e.type == EventType.EXERCISE
            and e.origin == Origin.AUTO
            and e.start < horizon_end
            and e.end > horizon_start
        )
    ]
    state = repair_exercise_events(state, now, through)
    state = place_auto_exercise(state, now, through)
    state = place_weekend_study(state, now, through)
    state.shopping = shopping
    state.week_summary = compute_week_summary(state, now)
    return state


def prune_stale_auto_ahead(
    state: AppState,
    now: datetime,
    *,
    keep_weeks: int = 2,
) -> AppState:
    """Drop Auto events far ahead of the current week.

    Used to clear leftovers from eager multi-month planning. Lazily planned
    weeks the user has already visited beyond ``keep_weeks`` are also
    dropped and will be rebuilt on the next fetch of that week.
    """
    tz = _tz(state)
    start, _ = week_bounds(now, tz)
    end = start + timedelta(days=7 * max(1, keep_weeks))
    state = state.model_copy(deep=True)
    state.events = [
        e
        for e in state.events
        if e.origin != Origin.AUTO or e.start < end
    ]
    return state


def to_snapshot(state: AppState) -> PlanSnapshot:
    return PlanSnapshot(
        events=state.events,
        recipes=state.recipes,
        fridge=state.fridge,
        rules=state.rules,
        shopping=state.shopping,
        signals=signal_emit.emit_signals(state),
        week_summary=state.week_summary,
        timezone=app_config.default_timezone,
    )
