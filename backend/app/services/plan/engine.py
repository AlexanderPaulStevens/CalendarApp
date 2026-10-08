"""Plan orchestrator: week-scoped recalculate pipeline."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.config import settings as app_config
from app.ingredients.shelf_life import ensure_fridge_shelf_lives
from app.schemas import models
from app.services.plan import events as plan_events
from app.services.plan import exercise as plan_exercise
from app.services.plan import shopping as plan_shopping
from app.services.plan import study as plan_study
from app.services.plan import summary as plan_summary
from app.services.plan import work_meals as plan_work_meals
from app.signals import emit as signal_emit


def recalculate(
    state: models.AppState,
    now: datetime | None = None,
    through: date | None = None,
) -> models.AppState:
    """Replan Auto events for the single Mon–Sun week of ``through``."""
    now = now or datetime.now(timezone.utc)
    zone = plan_events.tz(state)
    anchor = through
    if anchor is None:
        anchor = plan_events.as_local(now, zone).date()
    week_start, week_end = plan_events.week_bounds(anchor, zone)

    state = state.model_copy(deep=True)
    state = ensure_fridge_shelf_lives(state)
    state.events = plan_events.dedupe_identical_events(state.events)

    state = plan_work_meals.place_anchors(state, week_start, week_end)
    state = plan_exercise.repair(state, now, week_start, week_end)
    state = plan_exercise.place(state, now, week_start, week_end)
    state = plan_work_meals.assign_recipes(state, week_start, week_end)
    state = plan_shopping.place_trips_and_lines(
        state, now, week_start, week_end
    )
    state = plan_exercise.recover(state, now, week_start, week_end)
    state = plan_work_meals.assign_recipes(state, week_start, week_end)
    state = plan_shopping.refresh_lines(state, now, week_start, week_end)
    state = plan_study.place_weekend(state, now, week_start, week_end)
    state.week_summary = plan_summary.compute_week_summary(
        state, now, week_start, week_end
    )
    return state


def prune_stale_auto_ahead(
    state: models.AppState,
    now: datetime,
    *,
    keep_weeks: int = 2,
) -> models.AppState:
    """Drop Auto events far ahead of the current week."""
    zone = plan_events.tz(state)
    start, _ = plan_events.week_bounds(now, zone)
    end = start + timedelta(days=7 * max(1, keep_weeks))
    state = state.model_copy(deep=True)
    state.events = [
        e
        for e in state.events
        if e.origin != models.Origin.AUTO or e.start < end
    ]
    return state


def to_snapshot(state: models.AppState) -> models.PlanSnapshot:
    return models.PlanSnapshot(
        events=state.events,
        recipes=state.recipes,
        fridge=state.fridge,
        rules=state.rules,
        shopping=state.shopping,
        signals=signal_emit.emit_signals(state),
        week_summary=state.week_summary,
        timezone=app_config.default_timezone,
    )
