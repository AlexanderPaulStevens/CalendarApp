"""Load, mutate, replan, and snapshot plan state."""

from __future__ import annotations

import datetime

from app.schemas import models
from app.services import plan_engine
from app.store import json_store


def _now() -> datetime.datetime:
    """Return the current UTC time used as the plan clock.

    Returns:
        The current time as a timezone-aware datetime in UTC.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def get_snapshot(
    anchor: datetime.date | None = None,
) -> models.PlanSnapshot:
    """Load state, replan the viewed Mon–Sun week, persist, and snapshot.

    Only the week containing ``anchor`` (default: today) is recalculated.
    Auto events in other weeks stay as persisted until those weeks are
    fetched. Snapshot events are limited to the viewed week;
    ``week_summary`` is for that week.
    """
    now = _now()
    state = json_store.store.load()
    state = plan_engine.recalculate(state, now, through=anchor)
    json_store.store.save(state)
    snap = plan_engine.to_snapshot(state)

    range_start, range_end = plan_engine.event_window_for_week(
        state, anchor, now
    )
    events = [
        e
        for e in snap.events
        if e.end >= range_start and e.start <= range_end
    ]
    events = plan_engine.mark_conflicts(events)
    # Shopping list matches store-trip events shown on this week's calendar.
    week_start = range_start.date()
    week_end = range_end.date()
    shopping = [
        line
        for line in snap.shopping
        if line.trip_date is not None
        and week_start <= line.trip_date < week_end
    ]
    summary = plan_engine.compute_week_summary(
        state, now, range_start, range_end
    )
    event_ids = {e.id for e in events}
    signals = [
        s
        for s in snap.signals
        if s.event_id in event_ids
        or (s.at >= range_start and s.at <= range_end)
    ]
    return snap.model_copy(
        update={
            "events": events,
            "week_summary": summary,
            "shopping": shopping,
            "signals": signals,
        }
    )


def apply(
    mutator,
    *,
    anchor: datetime.date | None = None,
) -> models.PlanSnapshot:
    """Deep-copy state, run mutator, replan the relevant week, persist.

    Recalculates only the Mon–Sun week containing ``anchor`` (default:
    today) — same lazy window as ``get_snapshot``.
    """
    now = _now()

    def wrap(state: models.AppState) -> models.AppState:
        """Copy state, apply the mutator, and recalculate the plan."""
        next_state = mutator(state.model_copy(deep=True))
        return plan_engine.recalculate(next_state, now, through=anchor)

    state = json_store.store.mutate(wrap)
    return plan_engine.to_snapshot(state)
