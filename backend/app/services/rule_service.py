"""Mutate catalog rules and return an updated plan snapshot."""

from __future__ import annotations

import fastapi

from app.schemas import models
from app.services import snapshot


def update_rule(rule_id: str, body: models.RuleUpdate) -> models.PlanSnapshot:
    """Patch a catalog Rule's enablement and/or parameters.

    Args:
        rule_id: Id of the rule to update.
        body: Fields to change. Unset fields are left as they are.
          ``parameters`` is shallow-merged into the existing map.

    Returns:
        The recalculated plan with the patched rule.

    Raises:
        HTTPException: 404 when the rule is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch the rule enablement and parameters."""
        for i, r in enumerate(state.rules):
            if r.id != rule_id:
                continue
            data = body.model_dump(exclude_unset=True)
            params = data.pop("parameters", None)
            updated = r.model_copy(update=data)
            if params is not None:
                merged = dict(updated.parameters or {})
                merged.update(params)
                updated = updated.model_copy(update={"parameters": merged})
            state.rules[i] = updated
            return state
        raise fastapi.HTTPException(status_code=404, detail="Rule not found")

    return snapshot.apply(mut)
