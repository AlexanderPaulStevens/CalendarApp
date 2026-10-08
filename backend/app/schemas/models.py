"""Domain Pydantic models for the planning calendar."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid4())


class RuleKey(str, Enum):
    WEEKLY_EXERCISE_GOAL = "weekly_exercise_goal"
    DAILY_MEALS = "daily_meals"
    WORK_SCHEDULE = "work_schedule"
    STUDY_SCHEDULE = "study_schedule"
    BATCH_SHOPPING = "batch_shopping"


class EventType(str, Enum):
    EXERCISE = "exercise"
    MEAL = "meal"
    SHOPPING = "shopping"
    WORK = "work"
    STUDY = "study"
    PERSONAL = "personal"


class Origin(str, Enum):
    USER = "user"
    AUTO = "auto"


class Activity(str, Enum):
    CYCLING = "cycling"
    GYM = "gym"


class Unit(str, Enum):
    G = "g"
    ML = "ml"


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
    # Usable days after purchase (incl. buy day through buy_date + days).
    # None = pantry / non-perishable; shopping may buy a full batch ahead.
    shelf_life_days: int | None = None
    expiration_date: date | None = None
    location: str = ""


class Rule(BaseModel):
    id: str = Field(default_factory=new_id)
    rule_key: RuleKey
    name: str
    explanation: str = ""
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class ShoppingLine(BaseModel):
    id: str = Field(default_factory=new_id)
    ingredient: str
    quantity: float
    unit: Unit = Unit.G
    # Local calendar date of the Auto store-trip this line belongs to.
    trip_date: date | None = None


class WorkBlock(BaseModel):
    """Weekday work window. weekday: 0=Monday … 6=Sunday."""

    weekday: int
    start_hour: float
    end_hour: float


def default_work_blocks() -> list[WorkBlock]:
    """Preferred work windows (~25h after lunch split; goal_hours caps at 24)."""
    return [
        WorkBlock(weekday=0, start_hour=9, end_hour=17),
        WorkBlock(weekday=2, start_hour=9, end_hour=12),
        WorkBlock(weekday=2, start_hour=13, end_hour=17),
        WorkBlock(weekday=3, start_hour=9, end_hour=17),
        WorkBlock(weekday=4, start_hour=13, end_hour=17),
    ]


def default_study_blocks() -> list[WorkBlock]:
    """Tue 9–12 & 13–17, Wed 9–12, Fri 9–12."""
    return [
        WorkBlock(weekday=1, start_hour=9, end_hour=12),
        WorkBlock(weekday=1, start_hour=13, end_hour=17),
        WorkBlock(weekday=2, start_hour=9, end_hour=12),
        WorkBlock(weekday=4, start_hour=9, end_hour=12),
    ]


class Event(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    type: EventType
    start: datetime
    end: datetime
    all_day: bool = False
    origin: Origin = Origin.USER
    conflict: bool = False
    activity: Activity | None = None
    completed: bool = False
    recipe_id: str | None = None
    portions: float = 1.0
    ingredient_name: str | None = None


class Signal(BaseModel):
    """Derived prep marker; not persisted and not an Event."""

    id: str
    template_key: str
    event_id: str
    title: str
    body: str
    at: datetime


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
    ingredient_name: str | None = None


class WeekSummary(BaseModel):
    completed_hours: float = 0
    planned_hours: float = 0
    remaining_hours: float = 0
    sessions_needed: int = 0
    feasible_days: int = 0
    feasible: bool = True
    max_possible_hours: float = 0
    goal_hours: float = 10.0


class AppState(BaseModel):
    events: list[Event] = Field(default_factory=list)
    recipes: list[Recipe] = Field(default_factory=list)
    fridge: list[FridgeItem] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    shopping: list[ShoppingLine] = Field(default_factory=list)
    week_summary: WeekSummary = Field(default_factory=WeekSummary)


class PlanSnapshot(BaseModel):
    events: list[Event]
    recipes: list[Recipe]
    fridge: list[FridgeItem]
    rules: list[Rule]
    shopping: list[ShoppingLine]
    signals: list[Signal] = Field(default_factory=list)
    week_summary: WeekSummary
    timezone: str = "Europe/Brussels"


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
    shelf_life_days: int | None = None
    expiration_date: date | None = None
    location: str = ""


class FridgeUpdate(BaseModel):
    name: str | None = None
    quantity: float | None = None
    unit: Unit | None = None
    minimum_quantity: float | None = None
    replenishment_quantity: float | None = None
    shelf_life_days: int | None = None
    expiration_date: date | None = None
    location: str | None = None


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    parameters: dict[str, Any] | None = None
    name: str | None = None
    explanation: str | None = None
