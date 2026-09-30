"""Application services that mutate state and recalculate the plan."""

from __future__ import annotations

import datetime

import fastapi

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
    view: models.CalendarView | None = None,
    anchor: datetime.date | None = None,
) -> models.PlanSnapshot:
    """Load state, recalculate the plan, persist it, and return a snapshot.

    When view is set, only events overlapping that calendar span (day,
    week, or month grid) around anchor are included. Other snapshot
    fields are unchanged. Anchor defaults to today in the app timezone.

    Args:
        view: Calendar span to filter events by. None keeps every event.
        anchor: Local date the view is centered on. Ignored when view is
          None. Defaults to today in the app timezone.

    Returns:
        The persisted plan, with events limited to the view when given.

    Raises:
        HTTPException: 400 when anchor is set without view.
    """
    if anchor is not None and view is None:
        raise fastapi.HTTPException(
            status_code=400,
            detail="anchor requires view (day, week, or month)",
        )

    state = json_store.store.load()
    state = plan_engine.recalculate(state, _now())
    json_store.store.save(state)
    snap = plan_engine.to_snapshot(state)

    if view is not None:
        range_start, range_end = plan_engine.event_window_for_view(
            state, view, anchor, _now()
        )
        events = [
            e
            for e in snap.events
            if e.end >= range_start and e.start <= range_end
        ]
        snap = snap.model_copy(update={"events": events})
    return snap


def _apply(mutator) -> models.PlanSnapshot:
    """Deep-copy state, run mutator, recalculate, persist, and snapshot.

    Args:
        mutator: Callable that takes a deep copy of AppState and returns
          the next AppState. It may raise HTTPException.

    Returns:
        A snapshot of the recalculated, persisted plan.
    """
    def wrap(state: models.AppState) -> models.AppState:
        """Copy state, apply the mutator, and recalculate the plan."""
        next_state = mutator(state.model_copy(deep=True))
        return plan_engine.recalculate(next_state, _now())

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
        if event.origin != models.Origin.SUGGESTED:
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
        if event.type == models.EventType.EXERCISE:
            tz = plan_engine._tz(state)
            local_day = plan_engine._as_local(event.start, tz).date()
            if local_day.weekday() < 5:
                count = plan_engine._exercise_count_on_date(
                    state.events, local_day, tz
                )
                if count >= state.settings.max_exercise_blocks_weekday:
                    raise fastapi.HTTPException(
                        status_code=400,
                        detail=(
                            "Only one exercise block is allowed on a weekday; "
                            "use the weekend for more."
                        ),
                    )
            earliest = state.settings.exercise_earliest_hour
            if plan_engine._as_local(event.start, tz).hour < earliest:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail=f"Exercise cannot start before {earliest}:00.",
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
    """Patch an event, mark it user-owned, and recheck schedule rules.

    Args:
        event_id: Id of the event to update.
        body: Fields to change. Unset fields are left as they are.

    Returns:
        The recalculated plan with the patched event.

    Raises:
        HTTPException: 404 when the id is missing. 409 when a timed
          event overlaps another timed event. 400 when weekday exercise
          exceeds the daily cap or starts before the earliest hour.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch the event and recheck overlap and exercise rules."""
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
            if updated.type == models.EventType.EXERCISE:
                tz = plan_engine._tz(state)
                local_day = plan_engine._as_local(updated.start, tz).date()
                if local_day.weekday() < 5:
                    count = sum(
                        1
                        for other in state.events
                        if other.id != event_id
                        and other.type == models.EventType.EXERCISE
                        and plan_engine._as_local(
                            other.start, tz
                        ).date()
                        == local_day
                    )
                    if count >= state.settings.max_exercise_blocks_weekday:
                        raise fastapi.HTTPException(
                            status_code=400,
                            detail=(
                                "Only one exercise block is "
                                "allowed on a weekday; "
                                "use the weekend for more."
                            ),
                        )
                earliest = state.settings.exercise_earliest_hour
                if plan_engine._as_local(updated.start, tz).hour < earliest:
                    raise fastapi.HTTPException(
                        status_code=400,
                        detail=f"Exercise cannot start before {earliest}:00.",
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


def complete_event(event_id: str) -> models.PlanSnapshot:
    """Mark an exercise completed or a meal eaten.

    A meal also deducts recipe ingredients times portions from matching
    fridge stock. Other event types are rejected.

    Args:
        event_id: Id of the exercise or meal to complete.

    Returns:
        The recalculated plan with the event marked done.

    Raises:
        HTTPException: 404 when the id is missing. 400 when the event
          is neither exercise nor a meal.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Mark the event done and deduct meal ingredients."""
        for i, e in enumerate(state.events):
            if e.id != event_id:
                continue
            if e.type == models.EventType.EXERCISE:
                state.events[i] = e.model_copy(
                    update={"completed": True, "origin": models.Origin.USER}
                )
            elif e.type == models.EventType.MEAL:
                recipe = next(
                    (r for r in state.recipes if r.id == e.recipe_id),
                    None,
                )
                if recipe and not e.eaten:
                    for line in recipe.ingredients:
                        for inv in state.fridge:
                            if inv.name.lower() == line.name.lower():
                                inv.quantity = max(
                                    0.0,
                                    inv.quantity
                                    - line.quantity * e.portions,
                                )
                                break
                state.events[i] = e.model_copy(
                    update={"eaten": True, "origin": models.Origin.USER}
                )
            else:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail="Only exercise or meal can be completed",
                )
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
        state.fridge.append(models.FridgeItem(**body.model_dump()))
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


def create_rule(body: models.RuleCreate) -> models.PlanSnapshot:
    """Add a planning rule.

    Args:
        body: Rule fields to store.

    Returns:
        The recalculated plan including the new rule.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Append the planning rule."""
        state.rules.append(models.Rule(**body.model_dump()))
        return state

    return _apply(mut)


def update_rule(rule_id: str, body: models.RuleUpdate) -> models.PlanSnapshot:
    """Patch a planning rule.

    Re-enabling a rule clears its suppress dismissals so suggestions can
    appear again.

    Args:
        rule_id: Id of the rule to update.
        body: Fields to change. Unset fields are left as they are.

    Returns:
        The recalculated plan with the patched rule.

    Raises:
        HTTPException: 404 when the rule is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch the rule and clear suppress dismissals when re-enabled."""
        for i, r in enumerate(state.rules):
            if r.id != rule_id:
                continue
            state.rules[i] = r.model_copy(
                update=body.model_dump(exclude_unset=True)
            )
            if body.enabled is True:
                state.dismissals = [
                    d
                    for d in state.dismissals
                    if not (d.rule_id == rule_id and d.mode == "suppress")
                ]
            return state
        raise fastapi.HTTPException(status_code=404, detail="Rule not found")

    return _apply(mut)


def delete_rule(rule_id: str) -> models.PlanSnapshot:
    """Remove a rule and its dismissals.

    Args:
        rule_id: Id of the rule to remove.

    Returns:
        The recalculated plan without that rule or its dismissals.

    Raises:
        HTTPException: 404 when the rule is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Drop the rule and its dismissals."""
        before = len(state.rules)
        state.rules = [r for r in state.rules if r.id != rule_id]
        if len(state.rules) == before:
            raise fastapi.HTTPException(
                status_code=404, detail="Rule not found"
            )
        state.dismissals = [d for d in state.dismissals if d.rule_id != rule_id]
        return state

    return _apply(mut)


def check_shopping(
    line_id: str, body: models.ShoppingCheck
) -> models.PlanSnapshot:
    """Set a shopping line's checked flag.

    Checking an unchecked line adds its quantity to matching fridge
    stock, or creates a fridge item, and drops auto shopping reminders
    for that ingredient.

    Args:
        line_id: Id of the shopping line to update.
        body: Desired checked state.

    Returns:
        The recalculated plan with the line updated.

    Raises:
        HTTPException: 404 when the line is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Set the checked flag and restock the fridge when newly checked."""
        for i, line in enumerate(state.shopping):
            if line.id != line_id:
                continue
            if body.checked and not line.checked:
                # Add to fridge stock
                found = False
                for inv in state.fridge:
                    if inv.name.lower() == line.ingredient.lower():
                        inv.quantity += line.quantity
                        found = True
                        break
                if not found:
                    state.fridge.append(
                        models.FridgeItem(
                            name=line.ingredient,
                            quantity=line.quantity,
                            unit=line.unit,
                        )
                    )
                # Remove auto shopping reminders for this ingredient
                state.events = [
                    e
                    for e in state.events
                    if not (
                        e.type == models.EventType.SHOPPING
                        and e.origin == models.Origin.AUTO
                        and (e.ingredient_name or "").lower()
                        == line.ingredient.lower()
                    )
                ]
            state.shopping[i] = line.model_copy(
                update={"checked": body.checked}
            )
            return state
        raise fastapi.HTTPException(
            status_code=404, detail="Shopping line not found"
        )

    return _apply(mut)


def update_settings(body: models.AppSettingsUpdate) -> models.PlanSnapshot:
    """Patch app settings and recalculate the plan.

    Args:
        body: Settings fields to change. Unset fields stay as they are.

    Returns:
        The recalculated plan using the patched settings.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Patch settings on the copied state."""
        state.settings = state.settings.model_copy(
            update=body.model_dump(exclude_unset=True)
        )
        return state

    return _apply(mut)


def rebuild_auto_blocks() -> models.PlanSnapshot:
    """Drop auto exercise/routine blocks and refill free time.

    Removes ``origin=auto`` exercise events and routine blocks, then runs
    a full recalculation so the engine can schedule new auto blocks into
    free windows. User-origin events are left unchanged. Ordinary CRUD
    mutations recalculate derived state only; they do not rebuild these
    blocks — call this when the auto schedule should be regenerated.

    Returns:
        The persisted plan after auto blocks are rebuilt.
    """
    state = json_store.store.mutate(
        lambda s: plan_engine.rebuild_auto_blocks(
            s.model_copy(deep=True), _now()
        )
    )
    return plan_engine.to_snapshot(state)


def _find_suggestion(
    state: models.AppState, suggestion_id: str
) -> models.Suggestion | None:
    """Return a suggestion or warning with this id, or None.

    Args:
        state: Plan state whose suggestions and warnings are searched.
        suggestion_id: Id to match.

    Returns:
        The matching suggestion or warning, or None when absent.
    """
    for s in state.suggestions + state.warnings:
        if s.id == suggestion_id:
            return s
    return None


def accept_suggestion(suggestion_id: str) -> models.PlanSnapshot:
    """Turn a suggestion into a user event as proposed.

    Exercise uses the proposed start, end, and activity. A meal is
    placed at 19:00 local today for 45 minutes.

    Args:
        suggestion_id: Id of the suggestion or warning to accept.

    Returns:
        The recalculated plan including the accepted event.

    Raises:
        HTTPException: 404 when the suggestion is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Append the proposed event as a user event."""
        sug = _find_suggestion(state, suggestion_id)
        if sug is None:
            raise fastapi.HTTPException(
                status_code=404, detail="Suggestion not found"
            )
        proposed = sug.proposed
        if sug.kind.value == "exercise" or proposed.get("type") == "exercise":
            start = datetime.datetime.fromisoformat(proposed["start"])
            end = datetime.datetime.fromisoformat(proposed["end"])
            raw_activity = proposed.get("activity")
            activity = (
                models.Activity(raw_activity)
                if isinstance(raw_activity, str)
                else raw_activity
            )
            state.events.append(
                models.Event(
                    title=proposed.get("title", sug.title),
                    type=models.EventType.EXERCISE,
                    start=start,
                    end=end,
                    origin=models.Origin.USER,
                    activity=activity,
                )
            )
        elif sug.kind.value == "meal" or proposed.get("type") == "meal":
            # Place dinner tonight if no start given
            tz = plan_engine._tz(state)
            local = plan_engine._as_local(_now(), tz)
            start = datetime.datetime(
                local.year, local.month, local.day, 19, 0, tzinfo=tz
            )
            state.events.append(
                models.Event(
                    title=proposed.get("title", sug.title),
                    type=models.EventType.MEAL,
                    start=start,
                    end=start.replace(minute=45),
                    origin=models.Origin.USER,
                    recipe_id=proposed.get("recipe_id"),
                    portions=1.0,
                )
            )
        return state

    return _apply(mut)


def modify_suggestion(
    suggestion_id: str, body: models.SuggestionModify
) -> models.PlanSnapshot:
    """Accept a suggestion as a user event after applying the given edits.

    Missing start and end fall back to the proposal, or to 19:00-19:45
    local for meals.

    Args:
        suggestion_id: Id of the suggestion or warning to accept.
        body: Optional overrides for title, times, activity, recipe,
          and portions.

    Returns:
        The recalculated plan including the edited event.

    Raises:
        HTTPException: 404 when the suggestion is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Append the edited proposal as a user event."""
        sug = _find_suggestion(state, suggestion_id)
        if sug is None:
            raise fastapi.HTTPException(
                status_code=404, detail="Suggestion not found"
            )
        proposed = dict(sug.proposed)
        if body.title is not None:
            proposed["title"] = body.title
        if body.start is not None:
            proposed["start"] = body.start.isoformat()
        if body.end is not None:
            proposed["end"] = body.end.isoformat()
        if body.activity is not None:
            proposed["activity"] = body.activity.value
        if body.recipe_id is not None:
            proposed["recipe_id"] = body.recipe_id
        if body.portions is not None:
            proposed["portions"] = body.portions

        if proposed.get("type") == "exercise" or sug.kind.value == "exercise":
            start = (
                body.start
                if body.start
                else datetime.datetime.fromisoformat(proposed["start"])
            )
            end = (
                body.end
                if body.end
                else datetime.datetime.fromisoformat(proposed["end"])
            )
            state.events.append(
                models.Event(
                    title=proposed.get("title", sug.title),
                    type=models.EventType.EXERCISE,
                    start=start,
                    end=end,
                    origin=models.Origin.USER,
                    activity=proposed.get("activity"),
                )
            )
        elif proposed.get("type") == "meal" or sug.kind.value == "meal":
            tz = plan_engine._tz(state)
            local = plan_engine._as_local(_now(), tz)
            start = body.start or datetime.datetime(
                local.year, local.month, local.day, 19, 0, tzinfo=tz
            )
            end = body.end or start.replace(minute=45)
            state.events.append(
                models.Event(
                    title=proposed.get("title", sug.title),
                    type=models.EventType.MEAL,
                    start=start,
                    end=end,
                    origin=models.Origin.USER,
                    recipe_id=proposed.get("recipe_id"),
                    portions=proposed.get("portions", 1.0),
                )
            )
        return state

    return _apply(mut)


def ignore_suggestion(suggestion_id: str) -> models.PlanSnapshot:
    """Dismiss this suggestion once with an ignore dismissal.

    Args:
        suggestion_id: Id of the suggestion or warning to ignore.

    Returns:
        The recalculated plan with the ignore dismissal recorded.

    Raises:
        HTTPException: 404 when the suggestion is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Record an ignore dismissal for the suggestion."""
        sug = _find_suggestion(state, suggestion_id)
        if sug is None:
            raise fastapi.HTTPException(
                status_code=404, detail="Suggestion not found"
            )
        fp = str(sug.proposed.get("fingerprint", sug.id))
        state.dismissals.append(
            models.Dismissal(
                suggestion_key=suggestion_id,
                mode="ignore",
                rule_id=sug.rule_id,
                condition_fingerprint=fp,
            )
        )
        return state

    return _apply(mut)


def suppress_suggestion(suggestion_id: str) -> models.PlanSnapshot:
    """Stop this kind of suggestion and disable its rule.

    Args:
        suggestion_id: Id of the suggestion or warning to suppress.

    Returns:
        The recalculated plan with the rule disabled.

    Raises:
        HTTPException: 404 when the suggestion is missing.
    """
    def mut(state: models.AppState) -> models.AppState:
        """Record a suppress dismissal and disable the rule."""
        sug = _find_suggestion(state, suggestion_id)
        if sug is None:
            raise fastapi.HTTPException(
                status_code=404, detail="Suggestion not found"
            )
        state.dismissals.append(
            models.Dismissal(
                suggestion_key=suggestion_id,
                mode="suppress",
                rule_id=sug.rule_id,
                condition_fingerprint="",
            )
        )
        # Also disable the rule when suppress ("don't suggest this again")
        for i, r in enumerate(state.rules):
            if r.id == sug.rule_id:
                state.rules[i] = r.model_copy(update={"enabled": False})
        return state

    return _apply(mut)
