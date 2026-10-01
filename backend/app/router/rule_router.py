from fastapi import APIRouter

from app.schemas.models import PlanSnapshot, RuleUpdate
from app.services import app_service

router = APIRouter(prefix="/rules", tags=["rules"])


@router.patch("/{rule_id}", response_model=PlanSnapshot)
def update_rule(rule_id: str, body: RuleUpdate) -> PlanSnapshot:
    """Patch enablement and/or parameters on a catalog Rule."""
    return app_service.update_rule(rule_id, body)
