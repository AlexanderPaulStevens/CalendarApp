"""Pipeline contracts for week-scoped recalculate."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.schemas import models
from app.services import plan_engine
from app.store import seed


def _monday_noon_utc(week_monday: date) -> datetime:
    return datetime(
        week_monday.year,
        week_monday.month,
        week_monday.day,
        10,
        0,
        tzinfo=timezone.utc,
    )


def test_always_wed_and_sat_shopping_trips() -> None:
    state = seed.build_seed_state()
    # Fixed week: Monday 2026-10-05.
    now = _monday_noon_utc(date(2026, 10, 5))
    out = plan_engine.recalculate(state, now, through=date(2026, 10, 5))
    zone = plan_engine.event_window_for_week(out, date(2026, 10, 5), now)
    week_start, week_end = zone

    shops = [
        e
        for e in out.events
        if e.type == models.EventType.SHOPPING
        and e.origin == models.Origin.AUTO
        and e.start < week_end
        and e.end > week_start
    ]
    days = sorted({e.start.astimezone().date().weekday() for e in shops})
    assert len(shops) == 2
    assert days == [2, 5]  # Wed, Sat


def test_user_shop_counts_toward_two() -> None:
    state = seed.build_seed_state()
    now = _monday_noon_utc(date(2026, 10, 5))
    zone_name = "Europe/Brussels"
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(zone_name)
    wed = datetime(2026, 10, 7, 18, 0, tzinfo=tz)
    state.events.append(
        models.Event(
            title="User shop",
            type=models.EventType.SHOPPING,
            start=wed,
            end=wed + timedelta(minutes=45),
            origin=models.Origin.USER,
        )
    )
    out = plan_engine.recalculate(state, now, through=date(2026, 10, 5))
    week_start, week_end = plan_engine.event_window_for_week(
        out, date(2026, 10, 5), now
    )
    auto_shops = [
        e
        for e in out.events
        if e.type == models.EventType.SHOPPING
        and e.origin == models.Origin.AUTO
        and e.start < week_end
        and e.end > week_start
    ]
    user_shops = [
        e
        for e in out.events
        if e.type == models.EventType.SHOPPING
        and e.origin == models.Origin.USER
        and e.start < week_end
        and e.end > week_start
    ]
    assert len(user_shops) == 1
    assert len(auto_shops) == 1
    assert auto_shops[0].start.astimezone().weekday() == 5


def test_meals_have_recipes_after_exercise() -> None:
    state = seed.build_seed_state()
    now = _monday_noon_utc(date(2026, 10, 5))
    out = plan_engine.recalculate(state, now, through=date(2026, 10, 5))
    week_start, week_end = plan_engine.event_window_for_week(
        out, date(2026, 10, 5), now
    )
    auto_meals = [
        e
        for e in out.events
        if e.type == models.EventType.MEAL
        and e.origin == models.Origin.AUTO
        and e.start < week_end
        and e.end > week_start
    ]
    assert auto_meals
    assert all(e.recipe_id for e in auto_meals)


def test_single_week_no_preload() -> None:
    state = seed.build_seed_state()
    now = _monday_noon_utc(date(2026, 10, 5))
    out = plan_engine.recalculate(state, now, through=date(2026, 10, 5))
    week_start, week_end = plan_engine.event_window_for_week(
        out, date(2026, 10, 5), now
    )
    next_monday = week_end
    auto_next = [
        e
        for e in out.events
        if e.origin == models.Origin.AUTO and e.start >= next_monday
    ]
    assert auto_next == []


def test_auto_work_and_study_use_typed_events() -> None:
    state = seed.build_seed_state()
    now = _monday_noon_utc(date(2026, 10, 5))
    out = plan_engine.recalculate(state, now, through=date(2026, 10, 5))
    week_start, week_end = plan_engine.event_window_for_week(
        out, date(2026, 10, 5), now
    )
    auto_work = [
        e
        for e in out.events
        if e.type == models.EventType.WORK
        and e.origin == models.Origin.AUTO
        and e.start < week_end
        and e.end > week_start
    ]
    auto_study = [
        e
        for e in out.events
        if e.type == models.EventType.STUDY
        and e.origin == models.Origin.AUTO
        and e.start < week_end
        and e.end > week_start
    ]
    assert auto_work
    assert auto_study
    from app.services.plan import work_meals as plan_work_meals

    hours = plan_work_meals.work_hours_in_range(
        out.events, week_start, week_end
    )
    # Default goal is 24h; Auto fills up to that within work_blocks.
    assert abs(hours - 24.0) < 1e-6


def test_user_work_reduces_auto_work_hours() -> None:
    state = seed.build_seed_state()
    now = _monday_noon_utc(date(2026, 10, 5))
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Brussels")
    # User already worked 8h on Monday morning/afternoon outside lunch.
    mon = datetime(2026, 10, 5, 9, 0, tzinfo=tz)
    state.events.append(
        models.Event(
            title="Deep work",
            type=models.EventType.WORK,
            start=mon,
            end=mon + timedelta(hours=8),
            origin=models.Origin.USER,
        )
    )
    out = plan_engine.recalculate(state, now, through=date(2026, 10, 5))
    week_start, week_end = plan_engine.event_window_for_week(
        out, date(2026, 10, 5), now
    )
    from app.services.plan import work_meals as plan_work_meals

    total = plan_work_meals.work_hours_in_range(out.events, week_start, week_end)
    auto_hours = sum(
        (e.end - e.start).total_seconds() / 3600.0
        for e in out.events
        if e.type == models.EventType.WORK
        and e.origin == models.Origin.AUTO
        and e.start < week_end
        and e.end > week_start
    )
    assert total <= 24.0 + 1e-6
    assert auto_hours <= 16.0 + 1e-6
    assert auto_hours >= 15.0
