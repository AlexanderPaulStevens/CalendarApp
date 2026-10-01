"""Closed catalog of Signal templates (prep markers before Events)."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import models


@dataclass(frozen=True)
class SignalTemplate:
    """One catalog entry that can emit a Signal for a matching Event."""

    key: str
    title: str
    body: str
    lead_minutes: int
    event_type: models.EventType
    activity: models.Activity | None = None
    recipe_name_contains: str | None = None


# Broad curated defaults: type/activity, optional recipe name match.
TEMPLATES: tuple[SignalTemplate, ...] = (
    # --- Gym ---
    SignalTemplate(
        key="gym_charge_watch",
        title="Charge watch",
        body="Put your watch on charge before the gym.",
        lead_minutes=120,
        event_type=models.EventType.EXERCISE,
        activity=models.Activity.GYM,
    ),
    SignalTemplate(
        key="gym_charge_headphones",
        title="Charge headphones",
        body="Charge headphones and phone for the gym.",
        lead_minutes=120,
        event_type=models.EventType.EXERCISE,
        activity=models.Activity.GYM,
    ),
    SignalTemplate(
        key="gym_pack_bag",
        title="Pack gym bag",
        body="Clothes, shoes, towel, lock (fill water at the gym).",
        lead_minutes=45,
        event_type=models.EventType.EXERCISE,
        activity=models.Activity.GYM,
    ),
    # --- Cycling ---
    SignalTemplate(
        key="cycling_checklist",
        title="Bike checklist",
        body="Helmet · shoes · glasses · spare tire · candy",
        lead_minutes=40,
        event_type=models.EventType.EXERCISE,
        activity=models.Activity.CYCLING,
    ),
    SignalTemplate(
        key="cycling_fill_bottles",
        title="Fill bottles",
        body="Fill water bottles and clip them in.",
        lead_minutes=15,
        event_type=models.EventType.EXERCISE,
        activity=models.Activity.CYCLING,
    ),
    # --- Shopping ---
    SignalTemplate(
        key="shopping_bring_bags",
        title="Grab shopping bags",
        body="Take reusable bags (and wallet / store card).",
        lead_minutes=15,
        event_type=models.EventType.SHOPPING,
    ),
    # --- Meals: overnight oats (recipe name match) ---
    SignalTemplate(
        key="meal_prep_overnight_oats",
        title="Prep overnight oats",
        body="Mix oats tonight so breakfast is ready in the morning.",
        lead_minutes=12 * 60,
        event_type=models.EventType.MEAL,
        recipe_name_contains="overnight oats",
    ),
)
