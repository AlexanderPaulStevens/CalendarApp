from fastapi import APIRouter

from app.schemas.models import PlanSnapshot, RuleCreate, RuleUpdate
from app.services import app_service

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("", response_model=PlanSnapshot)
def create_rule(body: RuleCreate) -> PlanSnapshot:
    """Create a planning rule and return the updated plan snapshot."""
    return app_service.create_rule(body)


@router.patch("/{rule_id}", response_model=PlanSnapshot)
def update_rule(rule_id: str, body: RuleUpdate) -> PlanSnapshot:
    """Patch a planning rule and return the updated plan snapshot."""
    return app_service.update_rule(rule_id, body)


@router.delete("/{rule_id}", response_model=PlanSnapshot)
def delete_rule(rule_id: str) -> PlanSnapshot:
    """Delete a planning rule and return the updated plan snapshot."""
    return app_service.delete_rule(rule_id)
