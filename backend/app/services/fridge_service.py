"""Mutate fridge inventory and return an updated plan snapshot."""

from __future__ import annotations

import fastapi

from app.ingredients.shelf_life import default_shelf_life_days
from app.schemas import models
from app.services import snapshot


def create_fridge_item(body: models.FridgeCreate) -> models.PlanSnapshot:
    """Add a fridge inventory item.

    Args:
        body: Fridge item fields to store.

    Returns:
        The recalculated plan including the new item.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Append the fridge item."""
        data = body.model_dump()
        if data.get("shelf_life_days") is None:
            data["shelf_life_days"] = default_shelf_life_days(body.name)
        state.fridge.append(models.FridgeItem(**data))
        return state

    return snapshot.apply(mut)


def update_fridge_item(
    item_id: str, body: models.FridgeUpdate
) -> models.PlanSnapshot:
    """Patch a fridge item.

    Args:
        item_id: Id of the fridge item to update.
        body: Fields to change. Unset fields are left as they are.

    Returns:
        The recalculated plan with the patched item.

    Raises:
        HTTPException: 404 when the item is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch the fridge item."""
        for i, item in enumerate(state.fridge):
            if item.id != item_id:
                continue
            state.fridge[i] = item.model_copy(
                update=body.model_dump(exclude_unset=True)
            )
            return state
        raise fastapi.HTTPException(
            status_code=404, detail="Fridge item not found"
        )

    return snapshot.apply(mut)


def delete_fridge_item(item_id: str) -> models.PlanSnapshot:
    """Remove a fridge item.

    Args:
        item_id: Id of the fridge item to remove.

    Returns:
        The recalculated plan without that item.

    Raises:
        HTTPException: 404 when the item is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Drop the fridge item, or raise when it is missing."""
        before = len(state.fridge)
        state.fridge = [i for i in state.fridge if i.id != item_id]
        if len(state.fridge) == before:
            raise fastapi.HTTPException(
                status_code=404, detail="Fridge item not found"
            )
        return state

    return snapshot.apply(mut)
