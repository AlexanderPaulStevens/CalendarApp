"""Public facade for the week-scoped plan engine."""

from __future__ import annotations

from app.services.plan import engine as plan_engine_impl
from app.services.plan import events as plan_events
from app.services.plan import summary as plan_summary

# Re-export the API used by snapshot/domain services and tests.
recalculate = plan_engine_impl.recalculate
prune_stale_auto_ahead = plan_engine_impl.prune_stale_auto_ahead
to_snapshot = plan_engine_impl.to_snapshot
week_bounds = plan_events.week_bounds
event_window_for_week = plan_events.event_window_for_week
overlaps = plan_events.overlaps
hours_between = plan_events.hours_between
mark_conflicts = plan_events.mark_conflicts
compute_week_summary = plan_summary.compute_week_summary
