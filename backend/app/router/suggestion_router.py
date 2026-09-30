from fastapi import APIRouter

from app.schemas.models import PlanSnapshot, SuggestionModify
from app.services import app_service

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.post("/{suggestion_id}/accept", response_model=PlanSnapshot)
def accept_suggestion(suggestion_id: str) -> PlanSnapshot:
    """Accept a suggestion as proposed and return the updated plan snapshot."""
    return app_service.accept_suggestion(suggestion_id)


@router.post("/{suggestion_id}/modify", response_model=PlanSnapshot)
def modify_suggestion(
    suggestion_id: str, body: SuggestionModify
) -> PlanSnapshot:
    """Accept a suggestion with edits and return the updated plan snapshot."""
    return app_service.modify_suggestion(suggestion_id, body)


@router.post("/{suggestion_id}/ignore", response_model=PlanSnapshot)
def ignore_suggestion(suggestion_id: str) -> PlanSnapshot:
    """Dismiss a suggestion once and return the updated plan snapshot."""
    return app_service.ignore_suggestion(suggestion_id)


@router.post("/{suggestion_id}/suppress", response_model=PlanSnapshot)
def suppress_suggestion(suggestion_id: str) -> PlanSnapshot:
    """Suppress a suggestion so similar ones stop appearing, then return the plan."""
    return app_service.suppress_suggestion(suggestion_id)
