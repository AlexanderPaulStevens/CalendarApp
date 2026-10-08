from fastapi import APIRouter

from app.schemas.models import PlanSnapshot, RecipeCreate, RecipeDraftRequest
from app.services import recipe_service

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.post("/draft", response_model=RecipeCreate)
def draft_recipe(body: RecipeDraftRequest) -> RecipeCreate:
    """Draft a recipe from a short message via OpenAI (not saved yet)."""
    return recipe_service.draft_recipe(body.message)


@router.post("", response_model=PlanSnapshot)
def create_recipe(body: RecipeCreate) -> PlanSnapshot:
    """Save a recipe to the meal library and return the updated plan snapshot."""
    return recipe_service.create_recipe(body)


@router.put("/{recipe_id}", response_model=PlanSnapshot)
def update_recipe(recipe_id: str, body: RecipeCreate) -> PlanSnapshot:
    """Replace a recipe and return the updated plan snapshot."""
    return recipe_service.update_recipe(recipe_id, body)


@router.delete("/{recipe_id}", response_model=PlanSnapshot)
def delete_recipe(recipe_id: str) -> PlanSnapshot:
    """Delete a recipe and return the updated plan snapshot."""
    return recipe_service.delete_recipe(recipe_id)
