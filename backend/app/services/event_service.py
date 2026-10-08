"""Mutate calendar events and return an updated plan snapshot."""

from __future__ import annotations

import fastapi

from app.schemas import models
from app.services import plan_engine
from app.services import snapshot


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
                # Daily meals stay on the calendar; User events may overlap
                # them and are marked conflicting rather than displacing meals.
                if e.type == models.EventType.MEAL:
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

    return snapshot.apply(mut)


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
                    if other.type == models.EventType.MEAL:
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

    return snapshot.apply(mut)


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

    return snapshot.apply(mut)
