from datetime import date

from fastapi import APIRouter, Query

from app.schemas.models import PlanSnapshot
from app.services import snapshot

router = APIRouter(prefix="/plan", tags=["plan"])


@router.get("", response_model=PlanSnapshot)
def get_plan(
    anchor: date | None = Query(
        None,
        description=(
            "Local calendar date in the week to show (YYYY-MM-DD). "
            "Defaults to today in the app timezone."
        ),
    ),
) -> PlanSnapshot:
    """Return the plan snapshot for the week containing anchor."""
    return snapshot.get_snapshot(anchor)
