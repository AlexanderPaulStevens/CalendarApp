from datetime import date

from fastapi import APIRouter, Query

from app.schemas.models import CalendarView, PlanSnapshot
from app.services import app_service

router = APIRouter(prefix="/plan", tags=["plan"])


@router.get("", response_model=PlanSnapshot)
def get_plan(
    view: CalendarView | None = Query(
        None,
        description="Calendar span to include events for: day, week, or month.",
    ),
    anchor: date | None = Query(
        None,
        description=(
            "Local calendar date the view is centered on (YYYY-MM-DD). "
            "Defaults to today in the app timezone when view is set."
        ),
    ),
) -> PlanSnapshot:
    """Return the plan snapshot, optionally limited to a calendar view."""
    return app_service.get_snapshot(view, anchor)


@router.post("/rebuild-auto-blocks", response_model=PlanSnapshot)
def rebuild_auto_blocks() -> PlanSnapshot:
    """Drop auto exercise/routine blocks and refill free time.

    Unlike ordinary mutations (which only recalculate derived plan state),
    this removes ``origin=auto`` exercise events and routine blocks for the
    current week, then recalculates so the engine can place new ones. User
    events are never moved or deleted.
    """
    return app_service.rebuild_auto_blocks()
