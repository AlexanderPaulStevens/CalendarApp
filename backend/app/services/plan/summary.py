"""Week exercise summary."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from app.rules import access as rules_access
from app.schemas import models
from app.services.plan import events as plan_events
from app.services.plan import params as plan_params


def compute_week_summary(
    state: models.AppState,
    now: datetime,
    week_start: datetime | None = None,
    week_end: datetime | None = None,
) -> models.WeekSummary:
    zone = plan_events.tz(state)
    if week_start is None or week_end is None:
        week_start, week_end = plan_events.week_bounds(now, zone)
    ex = rules_access.rule_params(state, models.RuleKey.WEEKLY_EXERCISE_GOAL)
    goal = plan_params.as_float(ex, "goal_hours", 10.0)
    session_min = plan_params.as_float(ex, "session_min_hours", 1.0)
    session_max = plan_params.as_float(ex, "session_max_hours", 3.0)
    max_hours = plan_params.as_float(ex, "max_exercise_hours_per_day", 3.0)

    completed = 0.0
    planned = 0.0
    exercise_events = [
        e
        for e in state.events
        if e.type == models.EventType.EXERCISE
        and e.start < week_end
        and e.end > week_start
    ]
    for e in exercise_events:
        h = plan_events.hours_between(
            max(e.start, week_start), min(e.end, week_end)
        )
        if e.completed or e.end <= now:
            completed += h
        else:
            planned += h

    remaining = max(0.0, goal - completed - planned)

    feasible_days = 0
    max_possible = 0.0
    day = max(plan_events.as_local(now, zone), week_start)
    while day < week_end:
        local_day = plan_events.as_local(day, zone).date()
        day_start = datetime(
            local_day.year, local_day.month, local_day.day, 6, 0, tzinfo=zone
        )
        day_end = datetime(
            local_day.year, local_day.month, local_day.day, 22, 0, tzinfo=zone
        )
        if day_end <= now:
            day = day_start + timedelta(days=1)
            continue
        window_start = max(day_start, now)
        windows = plan_events.free_windows_for_day(
            window_start, day_end, state.events, session_min
        )
        day_capacity = 0.0
        for w_start, w_end in windows:
            day_capacity += min(
                session_max, plan_events.hours_between(w_start, w_end)
            )
        day_capacity = min(day_capacity, max_hours)
        if day_capacity >= session_min:
            feasible_days += 1
            max_possible += day_capacity
        day = day_start + timedelta(days=1)

    if remaining <= 0:
        sessions_needed = 0
    else:
        sessions_needed = int(math.ceil(remaining / session_max))

    return models.WeekSummary(
        completed_hours=round(completed, 2),
        planned_hours=round(planned, 2),
        remaining_hours=round(remaining, 2),
        sessions_needed=sessions_needed,
        feasible_days=feasible_days,
        feasible=remaining <= max_possible + 1e-6,
        max_possible_hours=round(max_possible, 2),
        goal_hours=goal,
    )
