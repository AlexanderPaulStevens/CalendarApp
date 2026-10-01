"""Seed defaults for an empty store."""

from __future__ import annotations

import json
from pathlib import Path

from app.ingredients.shelf_life import default_shelf_life_days
from app.rules.catalog import build_catalog_rules
from app.schemas.models import (
    AppState,
    FridgeItem,
    Recipe,
    Unit,
)

_RECIPES_PATH = Path(__file__).with_name("seed_recipes.json")


def _load_seed_recipes() -> list[Recipe]:
    raw = json.loads(_RECIPES_PATH.read_text(encoding="utf-8"))
    return [Recipe.model_validate(row) for row in raw]


def _fridge_from_recipes(recipes: list[Recipe]) -> list[FridgeItem]:
    """Stock enough of each ingredient for roughly a week of cooking."""
    totals: dict[tuple[str, Unit], float] = {}
    for recipe in recipes:
        for line in recipe.ingredients:
            key = (line.name, line.unit)
            totals[key] = totals.get(key, 0.0) + line.quantity

    fridge: list[FridgeItem] = []
    for (name, unit), weekly_use in sorted(totals.items()):
        # Cover ~1 week of meals that use this ingredient, rounded up.
        quantity = max(weekly_use * 0.5, weekly_use / 3, 100.0)
        quantity = round(quantity / 50) * 50
        minimum = max(50.0, round(weekly_use / 7 / 25) * 25)
        replenish = max(quantity, 200.0)
        fridge.append(
            FridgeItem(
                name=name,
                quantity=quantity,
                unit=unit,
                minimum_quantity=minimum,
                replenishment_quantity=replenish,
                shelf_life_days=default_shelf_life_days(name),
            )
        )
    return fridge


def build_seed_state() -> AppState:
    recipes = _load_seed_recipes()
    return AppState(
        events=[],
        recipes=recipes,
        fridge=_fridge_from_recipes(recipes),
        rules=build_catalog_rules(),
    )
