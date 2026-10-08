"""Resolve Rule instances and merged parameters from app state."""

from __future__ import annotations

from typing import Any

from app.rules.catalog import default_parameters
from app.schemas.models import AppState, Rule, RuleKey


def find_rule(state: AppState, key: RuleKey) -> Rule | None:
    """Return the Rule instance for ``key``, if present."""
    for rule in state.rules:
        if rule.rule_key == key:
            return rule
    return None


def rule_enabled(state: AppState, key: RuleKey) -> bool:
    """True when the catalog Rule exists and is enabled."""
    rule = find_rule(state, key)
    return rule is not None and rule.enabled


def rule_params(state: AppState, key: RuleKey) -> dict[str, Any]:
    """Defaults merged with the instance's parameters (instance wins)."""
    merged = default_parameters(key)
    rule = find_rule(state, key)
    if rule is not None:
        merged.update(rule.parameters or {})
    return merged


def ensure_catalog_rules(state: AppState) -> AppState:
    """Merge missing catalog keys into state; drop unknown keys."""
    from app.rules.catalog import build_catalog_rules
    from app.schemas.models import EventType

    by_key = {r.rule_key: r for r in state.rules}
    seed_by_key = {r.rule_key: r for r in build_catalog_rules()}
    updated = state.model_copy(deep=True)
    kept: list[Rule] = []
    for key, seed in seed_by_key.items():
        existing = by_key.get(key)
        if existing is None:
            kept.append(seed)
            continue
        # Instance values win, but drop keys no longer in the catalog defaults.
        merged_params = dict(seed.parameters)
        for param_key, value in (existing.parameters or {}).items():
            if param_key in seed.parameters:
                merged_params[param_key] = value
        kept.append(
            existing.model_copy(
                update={
                    "name": seed.name,
                    "explanation": seed.explanation,
                    "rule_key": key,
                    "parameters": merged_params,
                }
            )
        )
    updated.rules = kept

    # Legacy title-based Work/Study personal Events → typed Events.
    migrated: list = []
    changed = False
    for event in updated.events:
        if event.type == EventType.PERSONAL and event.title == "Work":
            migrated.append(event.model_copy(update={"type": EventType.WORK}))
            changed = True
        elif event.type == EventType.PERSONAL and event.title == "Study":
            migrated.append(event.model_copy(update={"type": EventType.STUDY}))
            changed = True
        else:
            migrated.append(event)
    if changed:
        updated.events = migrated
    return updated
