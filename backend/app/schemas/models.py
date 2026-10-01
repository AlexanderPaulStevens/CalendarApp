"""Domain Pydantic models for the planning calendar."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid4())


class EventType(str, Enum):
    EXERCISE = "exercise"
    SPORTING = "sporting"
    MEAL = "meal"
    SHOPPING = "shopping"
    PERSONAL = "personal"
    REST = "rest"


class Origin(str, Enum):
    USER = "user"
    AUTO = "auto"
    SUGGESTED = "suggested"


class Activity(str, Enum):
    CYCLING = "cycling"
    GYM = "gym"
    WALKING = "walking"


class Unit(str, Enum):
    G = "g"
    ML = "ml"


class Strength(str, Enum):
    MANDATORY = "mandatory"
    ADVISORY = "advisory"


class Scope(str, Enum):
    EVENT = "event"
    DAY = "day"
    WEEK = "week"
    MEAL = "meal"


class CalendarView(str, Enum):
    """Visible calendar span used to filter plan events."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class IngredientLine(BaseModel):
    name: str
    quantity: float
    unit: Unit = Unit.G


class Recipe(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    ingredients: list[IngredientLine] = Field(default_factory=list)
    calories: float = 0
    protein_g: float = 0
    carbohydrates_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    preparation_time_min: int = 0
    cuisine: str = ""
    meal_type: str = ""
    portion_size: str = "1 serving"
    storage_requirements: str = ""
    shelf_life_days: int | None = None
    freezer_suitable: bool = False


class FridgeItem(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    quantity: float
    unit: Unit = Unit.G
    minimum_quantity: float = 0
    replenishment_quantity: float = 0
    expiration_date: date | None = None
    location: str = ""


class Rule(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    condition_key: str
    scope: Scope
    action_key: str
    priority: int = 50
    strength: Strength = Strength.ADVISORY
    overridable: bool = True
    enabled: bool = True
    explanation: str = ""


class ShoppingLine(BaseModel):
    id: str = Field(default_factory=new_id)
    ingredient: str
    quantity: float
    unit: Unit = Unit.G
    checked: bool = False


class WorkBlock(BaseModel):
    """Weekday work window. weekday: 0=Monday … 6=Sunday."""

    weekday: int
    start_hour: float
    end_hour: float


def default_work_blocks() -> list[WorkBlock]:
    return [
        WorkBlock(weekday=0, start_hour=9, end_hour=17),  # Monday
        WorkBlock(weekday=2, start_hour=13, end_hour=17),  # Wednesday
        WorkBlock(weekday=3, start_hour=9, end_hour=17),  # Thursday
        WorkBlock(weekday=4, start_hour=13, end_hour=17),  # Friday
    ]


class AppSettings(BaseModel):
    timezone: str = "Europe/Amsterdam"
    weekly_exercise_goal_hours: float = 10.0
    session_min_hours: float = 1.5
    session_max_hours: float = 3.0
    activity_threshold_hours: float = 2.0
    walking_max_hours: float | None = None
    protein_target_g: float | None = None
    carbohydrate_target_g: float | None = None
    breakfast_hour: int = 8
    lunch_hour: int = 12
    dinner_hour: int = 18
    meal_duration_min: int = 45
    lunch_duration_min: int = 60  # 12:00–13:00 lunch break inside 9–5 work
    shopping_duration_min: int = 45
    exercise_earliest_hour: int = 7
    work_blocks: list[WorkBlock] = Field(default_factory=default_work_blocks)
    # Mon–Fri auto-plan: at most this many exercise blocks per day. Weekend: unlimited.
    max_exercise_blocks_weekday: int = 1
    # Batch shopping: one trip covers needs for this many days; shop this many days before run-out.
    shopping_batch_days: int = 7
    shopping_lead_days: int = 1


class Event(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    type: EventType
    start: datetime
    end: datetime
    all_day: bool = False
    origin: Origin = Origin.USER
    conflict: bool = False
    # Exercise
    activity: Activity | None = None
    completed: bool = False
    # Meal
    recipe_id: str | None = None
    portions: float = 1.0
    eaten: bool = False
    # Shopping reminder
    ingredient_name: str | None = None


class EventCreate(BaseModel):
    title: str
    type: EventType
    start: datetime
    end: datetime
    all_day: bool = False
    origin: Origin = Origin.USER
    activity: Activity | None = None
    completed: bool = False
    recipe_id: str | None = None
    portions: float = 1.0
    eaten: bool = False
    ingredient_name: str | None = None
    replace_event_ids: list[str] = Field(default_factory=list)


class RecipeDraftRequest(BaseModel):
    message: str


class EventUpdate(BaseModel):
    title: str | None = None
    type: EventType | None = None
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool | None = None
    activity: Activity | None = None
    completed: bool | None = None
    recipe_id: str | None = None
    portions: float | None = None
    eaten: bool | None = None
    ingredient_name: str | None = None


class SuggestionKind(str, Enum):
    EXERCISE = "exercise"
    MEAL = "meal"
    WARNING = "warning"


class Suggestion(BaseModel):
    id: str = Field(default_factory=new_id)
    rule_id: str
    kind: SuggestionKind
    explanation: str
    title: str
    # Proposed exercise/meal placement
    proposed: dict[str, Any] = Field(default_factory=dict)
    actions: list[str] = Field(
        default_factory=lambda: ["accept", "modify", "ignore", "suppress"]
    )


class WeekSummary(BaseModel):
    completed_hours: float = 0
    planned_hours: float = 0
    remaining_hours: float = 0
    sessions_needed: int = 0
    feasible_days: int = 0
    feasible: bool = True
    max_possible_hours: float = 0
    goal_hours: float = 10.0


class Dismissal(BaseModel):
    suggestion_key: str
    mode: Literal["ignore", "suppress"]
    rule_id: str
    condition_fingerprint: str = ""


class AppState(BaseModel):
    settings: AppSettings = Field(default_factory=AppSettings)
    events: list[Event] = Field(default_factory=list)
    recipes: list[Recipe] = Field(default_factory=list)
    fridge: list[FridgeItem] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    shopping: list[ShoppingLine] = Field(default_factory=list)
    dismissals: list[Dismissal] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    warnings: list[Suggestion] = Field(default_factory=list)
    week_summary: WeekSummary = Field(default_factory=WeekSummary)


class PlanSnapshot(BaseModel):
    events: list[Event]
    recipes: list[Recipe]
    fridge: list[FridgeItem]
    rules: list[Rule]
    shopping: list[ShoppingLine]
    settings: AppSettings
    week_summary: WeekSummary
    suggestions: list[Suggestion]
    warnings: list[Suggestion]


class SuggestionModify(BaseModel):
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    activity: Activity | None = None
    recipe_id: str | None = None
    portions: float | None = None


class RecipeCreate(BaseModel):
    name: str
    ingredients: list[IngredientLine] = Field(default_factory=list)
    calories: float = 0
    protein_g: float = 0
    carbohydrates_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    preparation_time_min: int = 0
    cuisine: str = ""
    meal_type: str = ""
    portion_size: str = "1 serving"
    storage_requirements: str = ""
    shelf_life_days: int | None = None
    freezer_suitable: bool = False


class FridgeCreate(BaseModel):
    name: str
    quantity: float
    unit: Unit = Unit.G
    minimum_quantity: float = 0
    replenishment_quantity: float = 0
    expiration_date: date | None = None
    location: str = ""


class FridgeUpdate(BaseModel):
    name: str | None = None
    quantity: float | None = None
    unit: Unit | None = None
    minimum_quantity: float | None = None
    replenishment_quantity: float | None = None
    expiration_date: date | None = None
    location: str | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    condition_key: str | None = None
    scope: Scope | None = None
    action_key: str | None = None
    priority: int | None = None
    strength: Strength | None = None
    overridable: bool | None = None
    enabled: bool | None = None
    explanation: str | None = None


class RuleCreate(BaseModel):
    name: str
    condition_key: str
    scope: Scope = Scope.WEEK
    action_key: str
    priority: int = 50
    strength: Strength = Strength.ADVISORY
    overridable: bool = True
    enabled: bool = True
    explanation: str = ""


class ShoppingCheck(BaseModel):
    checked: bool = True


class AppSettingsUpdate(BaseModel):
    timezone: str | None = None
    weekly_exercise_goal_hours: float | None = None
    session_min_hours: float | None = None
    session_max_hours: float | None = None
    activity_threshold_hours: float | None = None
    walking_max_hours: float | None = None
    protein_target_g: float | None = None
    carbohydrate_target_g: float | None = None
    breakfast_hour: int | None = None
    lunch_hour: int | None = None
    dinner_hour: int | None = None
    meal_duration_min: int | None = None
    lunch_duration_min: int | None = None
    shopping_duration_min: int | None = None
    exercise_earliest_hour: int | None = None
    work_blocks: list[WorkBlock] | None = None
    max_exercise_blocks_weekday: int | None = None
    shopping_batch_days: int | None = None
    shopping_lead_days: int | None = None
