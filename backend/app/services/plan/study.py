"""Weekend free-time Auto study packing."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.rules import access as rules_access
from app.schemas import models
from app.services.plan import events as plan_events
from app.services.plan import params as plan_params
from app.services.plan import work_meals as plan_work_meals


def _study_hours_on_date(event_list, day, zone) -> float:
    return sum(
        plan_events.hours_between(e.start, e.end)
        for e in event_list
        if plan_work_meals.is_study_event(e)
        and plan_events.as_local(e.start, zone).date() == day
    )


def place_weekend(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Pack Auto study into Sat/Sun free time toward weekend_goal_hours."""
    if not rules_access.rule_enabled(state, models.RuleKey.STUDY_SCHEDULE):
        return state

    state = state.model_copy(deep=True)
    zone = plan_events.tz(state)
    study = rules_access.rule_params(state, models.RuleKey.STUDY_SCHEDULE)
    goal = plan_params.as_float(study, "weekend_goal_hours", 14.0)
    earliest = max(
        0, min(23, plan_params.as_int(study, "weekend_earliest_hour", 7))
    )
    latest = max(
        earliest + 1,
        min(24, plan_params.as_int(study, "weekend_latest_hour", 22)),
    )
    block_min = plan_params.as_float(study, "weekend_block_min_hours", 2.0)
    block_max = plan_params.as_float(study, "weekend_block_max_hours", 4.0)
    today = plan_events.as_local(now, zone).date()

    monday = plan_events.as_local(week_start, zone).date()
    weekend_days = [
        d
        for d in (monday + timedelta(days=5), monday + timedelta(days=6))
        if d >= today and d < plan_events.as_local(week_end, zone).date()
    ]
    weekend_days = [
        d
        for d in weekend_days
        if not plan_work_meals.user_study_on_day(state.events, d, zone)
    ]
    if not weekend_days:
        return state

    # Drop existing Auto weekend study in this week so we reflow.
    state.events = [
        e
        for e in state.events
        if not (
            e.origin == models.Origin.AUTO
            and plan_work_meals.is_study_event(e)
            and plan_events.as_local(e.start, zone).date().weekday() >= 5
            and e.start < week_end
            and e.end > week_start
        )
    ]

    placed_hours = sum(
        _study_hours_on_date(state.events, d, zone) for d in weekend_days
    )
    remaining = max(0.0, goal - placed_hours)

    while remaining >= block_min - 1e-9:
        day = min(
            weekend_days,
            key=lambda d: (
                _study_hours_on_date(state.events, d, zone),
                d.toordinal(),
            ),
        )
        day_start = datetime(
            day.year, day.month, day.day, earliest, 0, tzinfo=zone
        )
        day_end = datetime(
            day.year, day.month, day.day, latest, 0, tzinfo=zone
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

        windows = plan_events.free_windows_for_day(
            day_start, day_end, state.events, block_min
        )
        if not windows:
            weekend_days = [d for d in weekend_days if d != day]
            if not weekend_days:
                break
            continue

        w_start, w_end = max(
            windows, key=lambda w: plan_events.hours_between(w[0], w[1])
        )
        fit = min(target, plan_events.hours_between(w_start, w_end))
        if fit < block_min - 1e-9:
            weekend_days = [d for d in weekend_days if d != day]
            if not weekend_days:
                break
            continue
        leftover = remaining - fit
        if (
            leftover < block_min - 1e-9
            and remaining
            <= plan_events.hours_between(w_start, w_end) + 1e-9
            and remaining <= block_max + 1e-9
        ):
            fit = remaining

        s = w_start
        e = w_start + timedelta(hours=fit)
        state.events.append(
            models.Event(
                title=plan_work_meals.ROUTINE_STUDY_TITLE,
                type=models.EventType.STUDY,
                start=s,
                end=e,
                origin=models.Origin.AUTO,
            )
        )
        remaining = max(0.0, remaining - fit)

    return state
