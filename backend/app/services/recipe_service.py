"""Mutate the meal library and draft recipes via OpenAI."""

from __future__ import annotations

import fastapi

from app.schemas import models
from app.services import openai_recipes
from app.services import snapshot


def draft_recipe(message: str) -> models.RecipeCreate:
    """Draft a recipe from a short message via OpenAI.

    The draft is returned to the caller and is not saved.

    Args:
        message: Short description of the recipe to draft.

    Returns:
        A recipe create payload that has not been persisted.

    Raises:
        HTTPException: 400 when the message is empty. 503 when
          OPENAI_API_KEY is unset. 502 when the provider request fails
          or returns no recipe.
    """
    return openai_recipes.draft_recipe_from_message(message)


def create_recipe(body: models.RecipeCreate) -> models.PlanSnapshot:
    """Append a recipe to the meal library.

    Args:
        body: Recipe fields to store.

    Returns:
        The recalculated plan including the new recipe.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Append the recipe to the library."""
        state.recipes.append(models.Recipe(**body.model_dump()))
        return state

    return snapshot.apply(mut)


def update_recipe(
    recipe_id: str, body: models.RecipeCreate
) -> models.PlanSnapshot:
    """Replace a recipe in place, keeping its id.

    Args:
        recipe_id: Id of the recipe to replace.
        body: Full recipe fields. The stored id is kept.

    Returns:
        The recalculated plan with the replaced recipe.

    Raises:
        HTTPException: 404 when the recipe is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Replace the recipe, keeping its id."""
        for i, r in enumerate(state.recipes):
            if r.id != recipe_id:
                continue
            state.recipes[i] = models.Recipe(id=recipe_id, **body.model_dump())
            return state
        raise fastapi.HTTPException(status_code=404, detail="Recipe not found")

    return snapshot.apply(mut)


def delete_recipe(recipe_id: str) -> models.PlanSnapshot:
    """Remove a recipe from the meal library.

    Args:
        recipe_id: Id of the recipe to remove.

    Returns:
        The recalculated plan without that recipe.

    Raises:
        HTTPException: 404 when the recipe is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Drop the recipe, or raise when it is missing."""
        before = len(state.recipes)
        state.recipes = [r for r in state.recipes if r.id != recipe_id]
        if len(state.recipes) == before:
            raise fastapi.HTTPException(
                status_code=404, detail="Recipe not found"
            )
        return state

    return snapshot.apply(mut)
