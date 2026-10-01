from fastapi import APIRouter

from app.schemas.models import PlanSnapshot, ShoppingCheck
from app.services import app_service

router = APIRouter(prefix="/shopping", tags=["shopping"])


@router.patch("/{line_id}", response_model=PlanSnapshot)
def check_shopping(line_id: str, body: ShoppingCheck) -> PlanSnapshot:
    """Mark a shopping line checked or unchecked and return the updated plan."""
    return app_service.check_shopping(line_id, body)
