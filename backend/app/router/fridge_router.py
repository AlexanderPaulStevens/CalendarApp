from fastapi import APIRouter

from app.schemas.models import FridgeCreate, FridgeUpdate, PlanSnapshot
from app.services import fridge_service

router = APIRouter(prefix="/fridge", tags=["fridge"])


@router.post("", response_model=PlanSnapshot)
def create_fridge_item(body: FridgeCreate) -> PlanSnapshot:
    """Add a fridge item and return the updated plan snapshot."""
    return fridge_service.create_fridge_item(body)


@router.patch("/{item_id}", response_model=PlanSnapshot)
def update_fridge_item(item_id: str, body: FridgeUpdate) -> PlanSnapshot:
    """Patch a fridge item and return the updated plan snapshot."""
    return fridge_service.update_fridge_item(item_id, body)


@router.delete("/{item_id}", response_model=PlanSnapshot)
def delete_fridge_item(item_id: str) -> PlanSnapshot:
    """Delete a fridge item and return the updated plan snapshot."""
    return fridge_service.delete_fridge_item(item_id)
