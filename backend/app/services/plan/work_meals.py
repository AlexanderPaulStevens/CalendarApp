"""Work, weekday study, and meal anchors + recipe assignment."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.rules import access as rules_access
from app.rules import catalog as rules_catalog
from app.schemas import models
from app.services.plan import events as plan_events
from app.services.plan import params as plan_params

ROUTINE_WORK_TITLE = "Work"
ROUTINE_STUDY_TITLE = "Study"


def is_routine_event(e: models.Event) -> bool:
    if e.origin != models.Origin.AUTO:
        return False
    if e.type in (models.EventType.WORK, models.EventType.STUDY):
        return True
    # Legacy Auto personal Work/Study before typed Events.
    if e.type == models.EventType.PERSONAL and e.title in (
        ROUTINE_WORK_TITLE,
        ROUTINE_STUDY_TITLE,
    ):
        return True
    if e.type == models.EventType.MEAL:
        return True
    return False


def is_work_event(e: models.Event) -> bool:
    if e.type == models.EventType.WORK:
        return True
    return (
        e.type == models.EventType.PERSONAL and e.title == ROUTINE_WORK_TITLE
    )


def is_study_event(e: models.Event) -> bool:
    if e.type == models.EventType.STUDY:
        return True
    return (
        e.type == models.EventType.PERSONAL and e.title == ROUTINE_STUDY_TITLE
    )


def work_hours_in_range(
    event_list: list[models.Event],
    range_start: datetime,
    range_end: datetime,
) -> float:
    total = 0.0
    for e in event_list:
        if not is_work_event(e):
            continue
        if e.all_day:
            continue
        if not (e.start < range_end and e.end > range_start):
            continue
        clip_start = max(e.start, range_start)
        clip_end = min(e.end, range_end)
        total += plan_events.hours_between(clip_start, clip_end)
    return total


def user_study_on_day(
    event_list: list[models.Event],
    local_date: date,
    zone: ZoneInfo | timezone,
) -> bool:
    for e in event_list:
        if e.origin != models.Origin.USER:
            continue
        if not is_study_event(e):
            continue
        if plan_events.as_local(e.start, zone).date() == local_date:
            return True
    return False


def _user_meal_covers_slot(
    event_list: list[models.Event],
    recipes: list[models.Recipe],
    local_date: date,
    meal_type: str,
    hour: int,
    zone: ZoneInfo | timezone,
) -> bool:
    recipe_types = {
        r.id: (r.meal_type or "").lower() for r in recipes
    }
    want = meal_type.lower()
    for e in event_list:
        if e.type != models.EventType.MEAL or e.origin != models.Origin.USER:
            continue
        local = plan_events.as_local(e.start, zone)
        if local.date() != local_date:
            continue
        if local.hour == hour:
            return True
        if e.recipe_id and recipe_types.get(e.recipe_id) == want:
            return True
    return False


def _lunch_break_bounds(
    local_date: date,
    meals: dict[str, Any],
    zone: ZoneInfo | timezone,
) -> tuple[datetime, datetime]:
    start = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        plan_params.as_int(meals, "lunch_hour", 12),
        0,
        tzinfo=zone,
    )
    end = start + timedelta(
        minutes=plan_params.as_int(meals, "lunch_duration_min", 60)
    )
    return start, end


def _work_segments_around_lunch(
    block_start: datetime,
    block_end: datetime,
    lunch_start: datetime,
    lunch_end: datetime,
) -> list[tuple[datetime, datetime]]:
    if not plan_events.overlaps(
        block_start, block_end, lunch_start, lunch_end
    ):
        return [(block_start, block_end)] if block_start < block_end else []
    segments: list[tuple[datetime, datetime]] = []
    if block_start < lunch_start:
        segments.append((block_start, min(lunch_start, block_end)))
    if lunch_end < block_end:
        segments.append((max(lunch_end, block_start), block_end))
    return [(s, e) for s, e in segments if s < e]


def _block_span(
    local_date: date,
    start_hour: float,
    end_hour: float,
    zone: ZoneInfo | timezone,
) -> tuple[datetime, datetime]:
    start_h = int(start_hour)
    start_m = int(round((start_hour - start_h) * 60))
    end_h = int(end_hour)
    end_m = int(round((end_hour - end_h) * 60))
    block_start = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        start_h,
        start_m,
        tzinfo=zone,
    )
    block_end = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        end_h,
        end_m,
        tzinfo=zone,
    )
    return block_start, block_end


def _place_auto_work(
    state: models.AppState,
    week_start: datetime,
    week_end: datetime,
    zone: ZoneInfo | timezone,
    work: dict[str, Any],
    meals: dict[str, Any],
) -> None:
    """Fill Auto work into work_blocks until goal_hours (User hours first)."""
    goal = plan_params.as_float(work, "goal_hours", 24.0)
    remaining = max(
        0.0, goal - work_hours_in_range(state.events, week_start, week_end)
    )
    if remaining <= 1e-9:
        return

    day = week_start
    while day < week_end and remaining > 1e-9:
        local_date = plan_events.as_local(day, zone).date()
        weekday = local_date.weekday()
        lunch_start, lunch_end = _lunch_break_bounds(local_date, meals, zone)

        for block in rules_catalog.work_blocks_from_params(work):
            if block.weekday != weekday:
                continue
            if remaining <= 1e-9:
                break
            block_start, block_end = _block_span(
                local_date, block.start_hour, block.end_hour, zone
            )
            for seg_start, seg_end in _work_segments_around_lunch(
                block_start, block_end, lunch_start, lunch_end
            ):
                if remaining <= 1e-9:
                    break
                windows = plan_events.free_windows_for_day(
                    seg_start, seg_end, state.events, min_hours=0.25
                )
                for win_start, win_end in windows:
                    if remaining <= 1e-9:
                        break
                    fit = min(
                        remaining,
                        plan_events.hours_between(win_start, win_end),
                    )
                    if fit < 0.25 - 1e-9:
                        continue
                    placed_end = win_start + timedelta(hours=fit)
                    state.events.append(
                        models.Event(
                            title=ROUTINE_WORK_TITLE,
                            type=models.EventType.WORK,
                            start=win_start,
                            end=placed_end,
                            origin=models.Origin.AUTO,
                        )
                    )
                    remaining = max(0.0, remaining - fit)

        day = day + timedelta(days=1)


def place_anchors(
    state: models.AppState,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Place Auto work, weekday study, and meal clock slots (no recipes)."""
    zone = plan_events.tz(state)
    meals = rules_access.rule_params(state, models.RuleKey.DAILY_MEALS)
    work = rules_access.rule_params(state, models.RuleKey.WORK_SCHEDULE)
    study = rules_access.rule_params(state, models.RuleKey.STUDY_SCHEDULE)
    state = state.model_copy(deep=True)
    state.events = [
        e
        for e in state.events
        if not (
            is_routine_event(e)
            and e.start < week_end
            and e.end > week_start
        )
    ]

    place_work = rules_access.rule_enabled(
        state, models.RuleKey.WORK_SCHEDULE
    )
    place_study = rules_access.rule_enabled(
        state, models.RuleKey.STUDY_SCHEDULE
    )
    place_meals = rules_access.rule_enabled(
        state, models.RuleKey.DAILY_MEALS
    )
    if not place_work and not place_study and not place_meals:
        return state

    if place_work:
        _place_auto_work(state, week_start, week_end, zone, work, meals)

    day = week_start
    while day < week_end:
        local_date = plan_events.as_local(day, zone).date()
        weekday = local_date.weekday()

        if place_study and not user_study_on_day(
            state.events, local_date, zone
        ):
            for block in rules_catalog.study_blocks_from_params(study):
                if block.weekday != weekday:
                    continue
                block_start, block_end = _block_span(
                    local_date, block.start_hour, block.end_hour, zone
                )
                if block_start >= block_end:
                    continue
                state.events.append(
                    models.Event(
                        title=ROUTINE_STUDY_TITLE,
                        type=models.EventType.STUDY,
                        start=block_start,
                        end=block_end,
                        origin=models.Origin.AUTO,
                    )
                )

        if place_meals:
            meal_slots = [
                (
                    "Breakfast",
                    plan_params.as_int(meals, "breakfast_hour", 8),
                    "breakfast",
                    plan_params.as_int(meals, "meal_duration_min", 45),
                ),
                (
                    "Lunch",
                    plan_params.as_int(meals, "lunch_hour", 12),
                    "lunch",
                    plan_params.as_int(meals, "lunch_duration_min", 60),
                ),
                (
                    "Dinner",
                    plan_params.as_int(meals, "dinner_hour", 18),
                    "dinner",
                    plan_params.as_int(meals, "meal_duration_min", 45),
                ),
            ]
            for title, hour, meal_type, duration_min in meal_slots:
                if _user_meal_covers_slot(
                    state.events,
                    state.recipes,
                    local_date,
                    meal_type,
                    hour,
                    zone,
                ):
                    continue
                preferred = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    hour,
                    0,
                    tzinfo=zone,
                )
                state.events.append(
                    models.Event(
                        title=title,
                        type=models.EventType.MEAL,
                        start=preferred,
                        end=preferred + timedelta(minutes=duration_min),
                        origin=models.Origin.AUTO,
                        recipe_id=None,
                        portions=1.0,
                    )
                )

        day = day + timedelta(days=1)

    return state


def _exercise_hours_before(
    state: models.AppState,
    local_date: date,
    before: datetime,
    zone: ZoneInfo | timezone,
) -> tuple[float, float]:
    total = 0.0
    cycling = 0.0
    for e in state.events:
        if e.type != models.EventType.EXERCISE:
            continue
        if plan_events.as_local(e.start, zone).date() != local_date:
            continue
        if e.end > before:
            continue
        h = plan_events.hours_between(e.start, e.end)
        total += h
        if e.activity == models.Activity.CYCLING:
            cycling += h
    return total, cycling


def _pick_recipe(
    state: models.AppState,
    meal_type: str,
    *,
    slot_key: str = "",
    used_ids: set[str] | None = None,
    allow_repeat: bool = False,
    prefer_protein: bool = False,
    prefer_carb_protein: bool = False,
) -> str | None:
    typed = [r for r in state.recipes if r.meal_type.lower() == meal_type]
    pool = typed or list(state.recipes)
    if not pool:
        return None
    used = used_ids or set()
    fresh = [r for r in pool if r.id not in used]
    if fresh:
        pool = fresh
    elif not allow_repeat:
        return None
    if prefer_carb_protein:
        pool = sorted(
            pool,
            key=lambda r: (r.carbohydrates_g + r.protein_g, r.protein_g),
            reverse=True,
        )
        pool = pool[: max(1, min(3, len(pool)))]
    elif prefer_protein:
        pool = sorted(pool, key=lambda r: r.protein_g, reverse=True)
        pool = pool[: max(1, min(3, len(pool)))]
    rng = random.Random(slot_key or meal_type)
    return rng.choice(pool).id


def assign_recipes(
    state: models.AppState,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Assign recipes to Auto meals in the week from exercise-before prefs."""
    if not rules_access.rule_enabled(state, models.RuleKey.DAILY_MEALS):
        return state

    zone = plan_events.tz(state)
    meals = rules_access.rule_params(state, models.RuleKey.DAILY_MEALS)
    threshold = plan_params.as_float(
        meals, "activity_threshold_hours", 2.0
    )
    state = state.model_copy(deep=True)

    auto_meals = sorted(
        [
            e
            for e in state.events
            if e.type == models.EventType.MEAL
            and e.origin == models.Origin.AUTO
            and e.start < week_end
            and e.end > week_start
        ],
        key=lambda e: e.start,
    )
    used_recipe_ids: set[str] = {
        e.recipe_id
        for e in state.events
        if e.type == models.EventType.MEAL
        and e.recipe_id
        and e.origin == models.Origin.USER
        and e.start < week_end
        and e.end > week_start
    }

    hour_to_type = {
        plan_params.as_int(meals, "breakfast_hour", 8): "breakfast",
        plan_params.as_int(meals, "lunch_hour", 12): "lunch",
        plan_params.as_int(meals, "dinner_hour", 18): "dinner",
    }

    updated: dict[str, models.Event] = {}
    for meal in auto_meals:
        local = plan_events.as_local(meal.start, zone)
        local_date = local.date()
        meal_type = hour_to_type.get(local.hour, "lunch")
        if meal.title.lower() in ("breakfast", "lunch", "dinner"):
            meal_type = meal.title.lower()
        elif meal.recipe_id:
            recipe = next(
                (r for r in state.recipes if r.id == meal.recipe_id), None
            )
            if recipe and recipe.meal_type:
                meal_type = recipe.meal_type.lower()

        ex_h, cyc_h = _exercise_hours_before(
            state, local_date, meal.start, zone
        )
        prefer_carb = cyc_h >= threshold
        prefer_protein = ex_h >= threshold
        allow_repeat = meal_type == "breakfast"
        slot_key = f"{local_date.isoformat()}:{meal_type}"
        recipe_id = _pick_recipe(
            state,
            meal_type,
            slot_key=slot_key,
            used_ids=used_recipe_ids,
            allow_repeat=allow_repeat,
            prefer_protein=prefer_protein and not prefer_carb,
            prefer_carb_protein=prefer_carb,
        )
        if not recipe_id and meal_type == "lunch":
            recipe_id = _pick_recipe(
                state,
                "dinner",
                slot_key=f"{slot_key}:fallback",
                used_ids=used_recipe_ids,
                allow_repeat=False,
                prefer_protein=prefer_protein and not prefer_carb,
                prefer_carb_protein=prefer_carb,
            )
        if not recipe_id:
            continue
        recipe = next(
            (r for r in state.recipes if r.id == recipe_id), None
        )
        used_recipe_ids.add(recipe_id)
        updated[meal.id] = meal.model_copy(
            update={
                "recipe_id": recipe_id,
                "title": recipe.name if recipe else meal.title,
            }
        )

    if not updated:
        return state
    state.events = [updated.get(e.id, e) for e in state.events]
    return state
