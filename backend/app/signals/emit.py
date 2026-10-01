"""Derive Signals from Events and the closed Signal template catalog."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from app.config import settings as app_config
from app.rules.access import rule_params
from app.schemas import models
from app.signals import catalog

# Match plan_engine routine titles (avoid importing plan_engine — cycle).
_WORK_TITLE = "Work"
_STUDY_TITLE = "Study"


def _recipe_by_id(state: models.AppState) -> dict[str, models.Recipe]:
    return {r.id: r for r in state.recipes}


def _tz() -> ZoneInfo | datetime.timezone:
    try:
        return ZoneInfo(app_config.default_timezone)
    except Exception:
        return datetime.timezone.utc


def _as_local(
    moment: datetime.datetime, tz: ZoneInfo | datetime.timezone
) -> datetime.datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc).astimezone(tz)
    return moment.astimezone(tz)


def _template_matches(
    template: catalog.SignalTemplate,
    event: models.Event,
    recipe: models.Recipe | None,
) -> bool:
    if event.type != template.event_type:
        return False
    if template.activity is not None and event.activity != template.activity:
        return False
    if template.recipe_name_contains:
        if recipe is None:
            return False
        needle = template.recipe_name_contains.casefold()
        if needle not in recipe.name.casefold():
            return False
    return True


def _is_trigger_host(event: models.Event) -> bool:
    """Work, study, or cooking (meal) — times when a Signal may fire."""
    if event.all_day:
        return False
    if event.type == models.EventType.MEAL:
        return True
    if event.type == models.EventType.PERSONAL and event.title in (
        _WORK_TITLE,
        _STUDY_TITLE,
    ):
        return True
    return False


def _trigger_windows(
    state: models.AppState,
    tz: ZoneInfo | datetime.timezone,
) -> list[tuple[datetime.datetime, datetime.datetime]]:
    windows: list[tuple[datetime.datetime, datetime.datetime]] = []
    for event in state.events:
        if not _is_trigger_host(event):
            continue
        start = _as_local(event.start, tz)
        end = _as_local(event.end, tz)
        if end > start:
            windows.append((start, end))
    windows.sort(key=lambda w: w[0])
    return windows


def _is_morning_gym(
    event: models.Event,
    local_start: datetime.datetime,
    morning_end_hour: int,
) -> bool:
    """True for gym sessions that start in the morning window (from 07:00)."""
    if event.type != models.EventType.EXERCISE:
        return False
    if event.activity != models.Activity.GYM:
        return False
    return local_start.hour < morning_end_hour


def _desired_at(
    event: models.Event,
    lead_minutes: int,
    *,
    tz: ZoneInfo | datetime.timezone,
    morning_end_hour: int,
) -> datetime.datetime:
    """Preferred instant before pinning into a work/study/meal window."""
    local_start = _as_local(event.start, tz)
    naive = local_start - datetime.timedelta(minutes=lead_minutes)

    if not _is_morning_gym(event, local_start, morning_end_hour):
        return naive

    prev_day = local_start.date() - datetime.timedelta(days=1)
    evening_anchor = datetime.datetime(
        prev_day.year,
        prev_day.month,
        prev_day.day,
        21,
        30,
        tzinfo=tz,
    )
    earliest_evening = datetime.datetime(
        prev_day.year,
        prev_day.month,
        prev_day.day,
        18,
        0,
        tzinfo=tz,
    )
    at = evening_anchor - datetime.timedelta(minutes=lead_minutes)
    if at < earliest_evening:
        at = earliest_evening
    return at


def _pin_to_trigger_window(
    desired: datetime.datetime,
    before: datetime.datetime,
    windows: list[tuple[datetime.datetime, datetime.datetime]],
    lead_minutes: int,
) -> datetime.datetime | None:
    """Snap a Signal into work/study/cooking; never during sport.

    Returns None when no suitable host window exists before the Event.
    """
    usable: list[tuple[datetime.datetime, datetime.datetime]] = []
    for start, end in windows:
        clipped_end = min(end, before)
        if start < clipped_end:
            usable.append((start, clipped_end))
    if not usable:
        return None

    containing = [
        (s, e) for s, e in usable if s <= desired < e
    ]
    if containing:
        return desired

    # Latest host window before the Event; keep relative lead order near end.
    best = max(usable, key=lambda w: w[1])
    pinned = best[1] - datetime.timedelta(minutes=lead_minutes)
    if pinned < best[0]:
        pinned = best[0]
    if pinned >= before:
        pinned = before - datetime.timedelta(minutes=1)
        if pinned < best[0]:
            return None
    return pinned


def emit_signals(state: models.AppState) -> list[models.Signal]:
    """Build Signals for timed Events from matching catalog templates.

    Morning gym prep prefers the evening before. Every Signal is pinned into
    a work, study, or meal block — never during a sporting Event. Signals
    with no such host window are omitted.
    """
    recipes = _recipe_by_id(state)
    tz = _tz()
    ex = rule_params(state, models.RuleKey.WEEKLY_EXERCISE_GOAL)
    morning_end = int(ex.get("morning_end_hour") or 12)
    morning_end = max(8, min(14, morning_end))
    windows = _trigger_windows(state, tz)
    out: list[models.Signal] = []

    for event in state.events:
        if event.all_day:
            continue
        recipe = recipes.get(event.recipe_id or "")
        before = _as_local(event.start, tz)
        target_end = _as_local(event.end, tz)
        # Host windows exclude the Event being prepared for (e.g. breakfast
        # must not host its own overnight-oats Signal).
        host_windows = [
            (s, e)
            for s, e in windows
            if not (
                abs((s - before).total_seconds()) < 1
                and abs((e - target_end).total_seconds()) < 1
            )
        ]
        for template in catalog.TEMPLATES:
            if not _template_matches(template, event, recipe):
                continue
            desired = _desired_at(
                event,
                template.lead_minutes,
                tz=tz,
                morning_end_hour=morning_end,
            )
            at = _pin_to_trigger_window(
                desired,
                before,
                host_windows,
                template.lead_minutes,
            )
            if at is None:
                continue
            out.append(
                models.Signal(
                    id=f"{event.id}:{template.key}",
                    template_key=template.key,
                    event_id=event.id,
                    title=template.title,
                    body=template.body,
                    at=at,
                )
            )

    out.sort(key=lambda s: (s.at, s.title))
    return out
