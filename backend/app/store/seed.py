"""Seed defaults for an empty store."""

from __future__ import annotations

from datetime import date, timedelta

from app.schemas.models import (
    AppSettings,
    AppState,
    FridgeItem,
    IngredientLine,
    Recipe,
    Rule,
    Scope,
    Strength,
    Unit,
)


def build_seed_state() -> AppState:
    settings = AppSettings()

    tofu_bowl = Recipe(
        name="Tofu rice bowl",
        ingredients=[
            IngredientLine(name="Tofu", quantity=200, unit=Unit.G),
            IngredientLine(name="Cooked rice", quantity=150, unit=Unit.G),
            IngredientLine(name="Broccoli", quantity=100, unit=Unit.G),
            IngredientLine(name="Edamame", quantity=80, unit=Unit.G),
            IngredientLine(name="Carrot", quantity=50, unit=Unit.G),
            IngredientLine(name="Tahini", quantity=15, unit=Unit.G),
            IngredientLine(name="Soy sauce", quantity=10, unit=Unit.ML),
            IngredientLine(name="Sesame oil", quantity=5, unit=Unit.ML),
        ],
        calories=520,
        protein_g=28,
        carbohydrates_g=48,
        fat_g=22,
        fiber_g=8,
        preparation_time_min=25,
        cuisine="Asian",
        meal_type="dinner",
        portion_size="1 bowl",
        storage_requirements="refrigerate",
        shelf_life_days=2,
        freezer_suitable=False,
    )
    oats = Recipe(
        name="Overnight oats",
        ingredients=[
            IngredientLine(name="Oats", quantity=80, unit=Unit.G),
            IngredientLine(name="Milk", quantity=200, unit=Unit.ML),
            IngredientLine(name="Banana", quantity=100, unit=Unit.G),
        ],
        calories=380,
        protein_g=12,
        carbohydrates_g=62,
        fat_g=8,
        fiber_g=7,
        preparation_time_min=5,
        cuisine="Western",
        meal_type="breakfast",
        portion_size="1 jar",
    )
    pasta = Recipe(
        name="Pasta primavera",
        ingredients=[
            IngredientLine(name="Pasta", quantity=100, unit=Unit.G),
            IngredientLine(name="Broccoli", quantity=120, unit=Unit.G),
            IngredientLine(name="Olive oil", quantity=15, unit=Unit.ML),
        ],
        calories=450,
        protein_g=14,
        carbohydrates_g=68,
        fat_g=14,
        fiber_g=6,
        preparation_time_min=20,
        cuisine="Italian",
        meal_type="lunch",
        vegan=True,
    )

    fridge = [
        FridgeItem(
            name="Tofu",
            quantity=400,
            unit=Unit.G,
            minimum_quantity=200,
            replenishment_quantity=600,
            expiration_date=date.today() + timedelta(days=10),
            location="fridge",
        ),
        FridgeItem(
            name="Broccoli",
            quantity=200,
            unit=Unit.G,
            minimum_quantity=100,
            replenishment_quantity=400,
            expiration_date=date.today() + timedelta(days=5),
            location="fridge",
        ),
        FridgeItem(
            name="Cooked rice",
            quantity=2000,
            unit=Unit.G,
            minimum_quantity=200,
            replenishment_quantity=1000,
            location="pantry",
        ),
        FridgeItem(
            name="Edamame",
            quantity=0,
            unit=Unit.G,
            minimum_quantity=100,
            replenishment_quantity=400,
            location="freezer",
        ),
        FridgeItem(
            name="Carrot",
            quantity=300,
            unit=Unit.G,
            minimum_quantity=100,
            replenishment_quantity=500,
            location="fridge",
        ),
        FridgeItem(
            name="Tahini",
            quantity=200,
            unit=Unit.G,
            minimum_quantity=50,
            replenishment_quantity=200,
            location="pantry",
        ),
        FridgeItem(
            name="Soy sauce",
            quantity=250,
            unit=Unit.ML,
            minimum_quantity=50,
            replenishment_quantity=250,
            location="pantry",
        ),
        FridgeItem(
            name="Sesame oil",
            quantity=100,
            unit=Unit.ML,
            minimum_quantity=20,
            replenishment_quantity=100,
            location="pantry",
        ),
        FridgeItem(
            name="Oats",
            quantity=500,
            unit=Unit.G,
            minimum_quantity=100,
            replenishment_quantity=500,
            location="pantry",
        ),
        FridgeItem(
            name="Milk",
            quantity=1000,
            unit=Unit.ML,
            minimum_quantity=200,
            replenishment_quantity=1000,
            expiration_date=date.today() + timedelta(days=7),
            location="fridge",
        ),
        FridgeItem(
            name="Banana",
            quantity=300,
            unit=Unit.G,
            minimum_quantity=100,
            replenishment_quantity=600,
            location="counter",
        ),
        FridgeItem(
            name="Pasta",
            quantity=500,
            unit=Unit.G,
            minimum_quantity=100,
            replenishment_quantity=500,
            location="pantry",
        ),
        FridgeItem(
            name="Olive oil",
            quantity=500,
            unit=Unit.ML,
            minimum_quantity=50,
            replenishment_quantity=500,
            location="pantry",
        ),
    ]

    rules = [
        Rule(
            name="Weekly exercise goal",
            condition_key="exercise_below_goal",
            scope=Scope.WEEK,
            action_key="suggest_exercise",
            priority=80,
            strength=Strength.ADVISORY,
            explanation=(
                "Exercise this week is below the weekly goal and enough days "
                "remain to place another valid session."
            ),
        ),
        Rule(
            name="Session minimum",
            condition_key="session_too_short",
            scope=Scope.EVENT,
            action_key="flag_session",
            priority=90,
            strength=Strength.MANDATORY,
            overridable=False,
            explanation="Exercise duration is under the session minimum.",
        ),
        Rule(
            name="Session maximum",
            condition_key="session_too_long",
            scope=Scope.EVENT,
            action_key="flag_session",
            priority=90,
            strength=Strength.MANDATORY,
            overridable=False,
            explanation="Exercise duration is over the session maximum.",
        ),
        Rule(
            name="Walking cap",
            condition_key="walking_over_cap",
            scope=Scope.WEEK,
            action_key="flag_walking",
            priority=85,
            strength=Strength.MANDATORY,
            overridable=False,
            explanation="Walking this week would exceed the configured walking maximum.",
        ),
        Rule(
            name="Low sport → protein meal",
            condition_key="sport_below_threshold",
            scope=Scope.DAY,
            action_key="suggest_protein_meal",
            priority=40,
            strength=Strength.ADVISORY,
            explanation="Sporting duration today is under the activity threshold.",
        ),
        Rule(
            name="Low exercise → protein meal",
            condition_key="exercise_below_threshold",
            scope=Scope.DAY,
            action_key="suggest_protein_meal",
            priority=40,
            strength=Strength.ADVISORY,
            explanation="Exercise duration today is under the activity threshold.",
        ),
        Rule(
            name="Active day protein",
            condition_key="exercise_at_threshold",
            scope=Scope.DAY,
            action_key="suggest_protein_target_meal",
            priority=50,
            strength=Strength.ADVISORY,
            explanation=(
                "Exercise duration today is at or above the activity threshold."
            ),
        ),
        Rule(
            name="Cycling carbs + protein",
            condition_key="cycling_at_threshold",
            scope=Scope.DAY,
            action_key="suggest_carb_protein_meal",
            priority=55,
            strength=Strength.ADVISORY,
            explanation=(
                "Cycling duration today is at or above the activity threshold."
            ),
        ),
        Rule(
            name="Missing ingredients",
            condition_key="meal_ingredient_shortfall",
            scope=Scope.MEAL,
            action_key="add_shopping",
            priority=95,
            strength=Strength.MANDATORY,
            overridable=False,
            explanation="A scheduled meal needs an ingredient that is not available.",
        ),
        Rule(
            name="Low stock warning",
            condition_key="stock_at_or_below_min",
            scope=Scope.DAY,
            action_key="warn_stock",
            priority=90,
            strength=Strength.MANDATORY,
            overridable=False,
            explanation=(
                "Available stock is at or below the minimum, or will be after "
                "planned meals."
            ),
        ),
        Rule(
            name="Three meals a day",
            condition_key="daily_meals",
            scope=Scope.DAY,
            action_key="place_daily_meals",
            priority=100,
            strength=Strength.MANDATORY,
            overridable=True,
            explanation=(
                "Place breakfast at 08:00, lunch at 12:00, and dinner at 18:00 every day."
            ),
        ),
        Rule(
            name="Working hours",
            condition_key="work_schedule",
            scope=Scope.WEEK,
            action_key="place_work_blocks",
            priority=100,
            strength=Strength.MANDATORY,
            overridable=True,
            explanation=(
                "Work blocks: Monday 09:00–17:00, Wednesday 13:00–17:00, "
                "Thursday 09:00–17:00, Friday 13:00–17:00. On 09:00–17:00 days, "
                "work is split around lunch 12:00–13:00 so meals do not overlap."
            ),
        ),
        Rule(
            name="No overlapping events",
            condition_key="timed_overlap",
            scope=Scope.EVENT,
            action_key="resolve_overlap",
            priority=100,
            strength=Strength.MANDATORY,
            overridable=False,
            explanation=(
                "Timed events must not overlap. The planner places or shifts "
                "auto events into free windows instead of stacking them."
            ),
        ),
        Rule(
            name="Spread exercise",
            condition_key="exercise_spread",
            scope=Scope.WEEK,
            action_key="spread_exercise",
            priority=85,
            strength=Strength.ADVISORY,
            explanation=(
                "Aim for 10h exercise per week from 07:00 onward. At most one "
                "exercise block on each weekday (Mon–Fri); prefer weekends for "
                "extra volume."
            ),
        ),
        Rule(
            name="Batch shopping ahead",
            condition_key="upcoming_meal_shortfall",
            scope=Scope.WEEK,
            action_key="batch_shopping",
            priority=92,
            strength=Strength.MANDATORY,
            overridable=True,
            explanation=(
                "From scheduled meals, buy ingredients ahead in one trip covering "
                "about a week of needs (default 7 days, 1 day lead). Avoid a "
                "separate shopping day for every run-out."
            ),
        ),
    ]

    # Calendar is filled by the planner (meals, work, exercise). Start empty.
    events = []

    return AppState(
        settings=settings,
        events=events,
        recipes=[tofu_bowl, oats, pasta],
        fridge=fridge,
        rules=rules,
    )
