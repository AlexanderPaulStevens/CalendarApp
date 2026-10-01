"""Application services that mutate state and recalculate the plan."""

from __future__ import annotations

import datetime

import fastapi

from app.ingredients.shelf_life import default_shelf_life_days
from app.schemas import models
from app.services import openai_recipes
from app.services import plan_engine
from app.store import json_store


def _now() -> datetime.datetime:
    """Return the current UTC time used as the plan clock.

    Returns:
        The current time as a timezone-aware datetime in UTC.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def get_snapshot(
    anchor: datetime.date | None = None,
) -> models.PlanSnapshot:
    """Load state, replan the viewed week (+ preload), persist, and snapshot.

    Only the week containing ``anchor`` (default: today) and a small preload
    window are recalculated. Auto events in other weeks stay as persisted
    until those weeks are fetched. Snapshot events are limited to the
    viewed week; ``week_summary`` is for that week.
    """
    now = _now()
    state = json_store.store.load()
    state = plan_engine.recalculate(state, now, through=anchor)
    json_store.store.save(state)
    snap = plan_engine.to_snapshot(state)

    range_start, range_end = plan_engine.event_window_for_week(
        state, anchor, now
    )
    events = [
        e
        for e in snap.events
        if e.end >= range_start and e.start <= range_end
    ]
    events = plan_engine.mark_conflicts(events)
    # Shopping list matches store-trip events shown on this week's calendar.
    week_start = range_start.date()
    week_end = range_end.date()
    shopping = [
        line
        for line in snap.shopping
        if line.trip_date is not None
        and week_start <= line.trip_date < week_end
    ]
    summary = plan_engine.compute_week_summary(
        state, now, range_start, range_end
    )
    event_ids = {e.id for e in events}
    signals = [
        s
        for s in snap.signals
        if s.event_id in event_ids
        or (s.at >= range_start and s.at <= range_end)
    ]
    return snap.model_copy(
        update={
            "events": events,
            "week_summary": summary,
            "shopping": shopping,
            "signals": signals,
        }
    )


def _apply(
    mutator,
    *,
    anchor: datetime.date | None = None,
) -> models.PlanSnapshot:
    """Deep-copy state, run mutator, replan the relevant week, persist.

    Recalculates only the week containing ``anchor`` (default: today) plus
    preload — same lazy window as ``get_snapshot``.
    """
    now = _now()

    def wrap(state: models.AppState) -> models.AppState:
        """Copy state, apply the mutator, and recalculate the plan."""
        next_state = mutator(state.model_copy(deep=True))
        return plan_engine.recalculate(next_state, now, through=anchor)

    state = json_store.store.mutate(wrap)
    return plan_engine.to_snapshot(state)


def create_event(body: models.EventCreate) -> models.PlanSnapshot:
    """Add an event, optionally replacing the given event ids.

    Non-suggested events are stored as user origin. Timed events that
    overlap another timed event are rejected. Weekday exercise that
    exceeds the daily cap or starts before the earliest hour is rejected.

    Args:
        body: Event fields. replace_event_ids lists events to remove
          before the overlap check.

    Returns:
        The recalculated plan including the new event.

    Raises:
        HTTPException: 409 when a timed event overlaps another timed
          event. 400 when weekday exercise exceeds the daily cap or
          starts before the earliest allowed hour.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Insert the event after overlap and exercise checks."""
        data = body.model_dump(exclude={"replace_event_ids"})
        event = models.Event(**data)
        event.origin = models.Origin.USER
        if body.replace_event_ids:
            replace = set(body.replace_event_ids)
            state.events = [e for e in state.events if e.id not in replace]
        else:
            replace = set()
        if not event.all_day:
            for e in state.events:
                if e.id in replace or e.all_day:
                    continue
                if plan_engine.overlaps(e.start, e.end, event.start, event.end):
                    raise fastapi.HTTPException(
                        status_code=409,
                        detail=(
                            "Events cannot overlap; "
                            "choose a free time slot."
                        ),
                    )
        state.events.append(event)
        return state

    return _apply(mut)


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


def update_event(
    event_id: str, body: models.EventUpdate
) -> models.PlanSnapshot:
    """Patch an event, claim it as User-owned, and recheck overlaps.

    Args:
        event_id: Id of the event to update.
        body: Fields to change. Unset fields are left as they are.

    Returns:
        The recalculated plan with the patched event.

    Raises:
        HTTPException: 404 when the id is missing. 409 when a timed
          event overlaps another timed event.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch the event and recheck overlap."""
        for i, e in enumerate(state.events):
            if e.id != event_id:
                continue
            data = body.model_dump(exclude_unset=True)
            updated = e.model_copy(update=data)
            updated.origin = models.Origin.USER
            if not updated.all_day:
                for other in state.events:
                    if other.id == event_id or other.all_day:
                        continue
                    if plan_engine.overlaps(
                        other.start, other.end, updated.start, updated.end
                    ):
                        raise fastapi.HTTPException(
                            status_code=409,
                            detail=(
                                "Events cannot overlap; "
                                "choose a free time slot."
                            ),
                        )
            state.events[i] = updated
            return state
        raise fastapi.HTTPException(status_code=404, detail="Event not found")

    return _apply(mut)


def delete_event(event_id: str) -> models.PlanSnapshot:
    """Remove an event by id.

    Args:
        event_id: Id of the event to remove.

    Returns:
        The recalculated plan without that event.

    Raises:
        HTTPException: 404 when the id is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Drop the event, or raise when it is missing."""
        before = len(state.events)
        state.events = [e for e in state.events if e.id != event_id]
        if len(state.events) == before:
            raise fastapi.HTTPException(
                status_code=404, detail="Event not found"
            )
        return state

    return _apply(mut)


def duplicate_event(event_id: str) -> models.PlanSnapshot:
    """Append a user-owned copy with a new id and a "(copy)" title.

    Args:
        event_id: Id of the event to copy.

    Returns:
        The recalculated plan including the copy.

    Raises:
        HTTPException: 404 when the source event is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Append a user-owned copy of the event."""
        for e in state.events:
            if e.id != event_id:
                continue
            copy = e.model_copy(deep=True)
            copy.id = models.new_id()
            copy.origin = models.Origin.USER
            copy.title = f"{e.title} (copy)"
            state.events.append(copy)
            return state
        raise fastapi.HTTPException(status_code=404, detail="Event not found")

    return _apply(mut)


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

    return _apply(mut)


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

    return _apply(mut)


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

    return _apply(mut)


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

    return _apply(mut)


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

    return _apply(mut)


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

    return _apply(mut)


def update_rule(rule_id: str, body: models.RuleUpdate) -> models.PlanSnapshot:
    """Patch a catalog Rule's enablement and/or parameters.

    Args:
        rule_id: Id of the rule to update.
        body: Fields to change. Unset fields are left as they are.
          ``parameters`` is shallow-merged into the existing map.

    Returns:
        The recalculated plan with the patched rule.

    Raises:
        HTTPException: 404 when the rule is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch the rule enablement and parameters."""
        for i, r in enumerate(state.rules):
            if r.id != rule_id:
                continue
            data = body.model_dump(exclude_unset=True)
            params = data.pop("parameters", None)
            updated = r.model_copy(update=data)
            if params is not None:
                merged = dict(updated.parameters or {})
                merged.update(params)
                updated = updated.model_copy(update={"parameters": merged})
            state.rules[i] = updated
            return state
        raise fastapi.HTTPException(status_code=404, detail="Rule not found")

    return _apply(mut)
