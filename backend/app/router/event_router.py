from fastapi import APIRouter

from app.schemas.models import EventCreate, EventUpdate, PlanSnapshot
from app.services import app_service

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=PlanSnapshot)
def create_event(body: EventCreate) -> PlanSnapshot:
    """Create a calendar event and return the updated plan snapshot."""
    return app_service.create_event(body)


@router.patch("/{event_id}", response_model=PlanSnapshot)
def update_event(event_id: str, body: EventUpdate) -> PlanSnapshot:
    """Patch an existing event and return the updated plan snapshot."""
    return app_service.update_event(event_id, body)


@router.delete("/{event_id}", response_model=PlanSnapshot)
def delete_event(event_id: str) -> PlanSnapshot:
    """Delete an event and return the updated plan snapshot."""
    return app_service.delete_event(event_id)


@router.post("/{event_id}/duplicate", response_model=PlanSnapshot)
def duplicate_event(event_id: str) -> PlanSnapshot:
    """Copy an event and return the updated plan snapshot."""
    return app_service.duplicate_event(event_id)


@router.post("/{event_id}/complete", response_model=PlanSnapshot)
def complete_event(event_id: str) -> PlanSnapshot:
    """Mark an exercise done or a meal eaten.

    Exercise: sets ``completed``. Meal: sets ``eaten`` and deducts recipe
    ingredients × portions from the fridge. Other event types return 400.
    """
    return app_service.complete_event(event_id)
