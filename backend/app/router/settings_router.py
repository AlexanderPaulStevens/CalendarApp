from fastapi import APIRouter

from app.schemas.models import AppSettingsUpdate, PlanSnapshot
from app.services import app_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.patch("", response_model=PlanSnapshot)
def update_settings(body: AppSettingsUpdate) -> PlanSnapshot:
    """Update app settings and return the updated plan snapshot."""
    return app_service.update_settings(body)
