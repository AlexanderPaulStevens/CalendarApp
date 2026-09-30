"""Deterministic plan recalculation engine."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.schemas.models import (
    Activity,
    AppSettings,
    AppState,
    CalendarView,
    Event,
    EventType,
    Origin,
    PlanSnapshot,
    ShoppingLine,
    Suggestion,
    SuggestionKind,
    Unit,
    WeekSummary,
    new_id,
)


def _tz(state: AppState) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(state.settings.timezone)
    except Exception:
        try:
            return ZoneInfo("Etc/UTC")
        except Exception:
            return timezone.utc


def _as_local(dt: datetime, tz: ZoneInfo | timezone) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def week_bounds(
    ref: datetime, tz: ZoneInfo | timezone
) -> tuple[datetime, datetime]:
    local = _as_local(ref, tz)
    monday_date = local.date() - timedelta(days=local.weekday())
    start = datetime(
        monday_date.year, monday_date.month, monday_date.day, tzinfo=tz
    )
    end = start + timedelta(days=7)
    return start, end


def view_bounds(
    view: CalendarView, anchor: date, tz: ZoneInfo | timezone
) -> tuple[datetime, datetime]:
    """Return the inclusive-exclusive event window for a calendar view.

    Day is midnight→next midnight on ``anchor``. Week is Monday→Monday for
    the week containing ``anchor``. Month is the 6-week grid starting on
    the Monday of the week that contains the first of ``anchor``'s month.
    Bounds use the app timezone.
    """
    if view == CalendarView.DAY:
        start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=tz)
        return start, start + timedelta(days=1)
    if view == CalendarView.WEEK:
        monday = anchor - timedelta(days=anchor.weekday())
        start = datetime(monday.year, monday.month, monday.day, tzinfo=tz)
        return start, start + timedelta(days=7)
    first = date(anchor.year, anchor.month, 1)
    grid_start = first - timedelta(days=first.weekday())
    start = datetime(
        grid_start.year, grid_start.month, grid_start.day, tzinfo=tz
    )
    return start, start + timedelta(days=42)


def event_window_for_view(
    state: AppState,
    view: CalendarView,
    anchor: date | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Resolve view/anchor to an event filter window in the app timezone."""
    tz = _tz(state)
    if anchor is None:
        anchor = _as_local(now, tz).date()
    return view_bounds(view, anchor, tz)


def hours_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600.0)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def mark_conflicts(events: list[Event]) -> list[Event]:
    updated = [e.model_copy(deep=True) for e in events]
    for e in updated:
        e.conflict = False
    timed = [e for e in updated if not e.all_day]
    for i, a in enumerate(timed):
        for b in timed[i + 1 :]:
            if overlaps(a.start, a.end, b.start, b.end):
                a.conflict = True
                b.conflict = True
    return updated


def available_qty(item, today: date) -> float:
    if item.expiration_date is not None and item.expiration_date < today:
        return 0.0
    return max(0.0, item.quantity)


def purchase_quantity(
    required: float,
    available: float,
    minimum: float,
    replenish: float,
) -> float:
    shortfall = max(0.0, required - available)
    projected = available - required + shortfall
    qty = shortfall
    if projected <= minimum and replenish > 0:
        qty = max(shortfall, replenish)
    return qty


def free_windows_for_day(
    day_start: datetime,
    day_end: datetime,
    events: list[Event],
    min_hours: float,
) -> list[tuple[datetime, datetime]]:
    """Return free intervals of at least min_hours within [day_start, day_end)."""
    blocking = sorted(
        [
            e
            for e in events
            if not e.all_day and overlaps(e.start, e.end, day_start, day_end)
        ],
        key=lambda e: e.start,
    )
    windows: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for e in blocking:
        start = max(cursor, day_start)
        end = min(e.start, day_end)
        if hours_between(start, end) >= min_hours - 1e-9:
            windows.append((start, end))
        cursor = max(cursor, e.end)
    if hours_between(cursor, day_end) >= min_hours - 1e-9:
        windows.append((cursor, day_end))
    return windows


def _timed_events_overlap_slot(
    events: list[Event], start: datetime, end: datetime
) -> bool:
    for e in events:
        if e.all_day:
            continue
        if overlaps(e.start, e.end, start, end):
            return True
    return False


def find_non_overlapping_slot(
    preferred_start: datetime,
    duration: timedelta,
    events: list[Event],
    search_start: datetime,
    search_end: datetime,
) -> tuple[datetime, datetime] | None:
    """Prefer preferred_start; otherwise first free window that fits duration."""
    preferred_end = preferred_start + duration
    if (
        preferred_start >= search_start
        and preferred_end <= search_end
        and not _timed_events_overlap_slot(events, preferred_start, preferred_end)
    ):
        return preferred_start, preferred_end

    min_hours = duration.total_seconds() / 3600.0
    for w_start, w_end in free_windows_for_day(
        search_start, search_end, events, min_hours
    ):
        # Prefer a window that contains the preferred start when possible.
        if w_start <= preferred_start and preferred_start + duration <= w_end:
            return preferred_start, preferred_start + duration
        slot_end = w_start + duration
        if slot_end <= w_end:
            return w_start, slot_end
    return None


def _lunch_break_bounds(
    local_date: date, settings: AppSettings, tz: ZoneInfo | timezone
) -> tuple[datetime, datetime]:
    start = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        settings.lunch_hour,
        0,
        tzinfo=tz,
    )
    end = start + timedelta(minutes=settings.lunch_duration_min)
    return start, end


def _work_segments_around_lunch(
    block_start: datetime,
    block_end: datetime,
    lunch_start: datetime,
    lunch_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Split a work block so lunch 12–1 can sit inside a 9–5 day without overlap."""
    if not overlaps(block_start, block_end, lunch_start, lunch_end):
        return [(block_start, block_end)] if block_start < block_end else []
    segments: list[tuple[datetime, datetime]] = []
    if block_start < lunch_start:
        segments.append((block_start, min(lunch_start, block_end)))
    if lunch_end < block_end:
        segments.append((max(lunch_end, block_start), block_end))
    return [(s, e) for s, e in segments if s < e]


def compute_week_summary(state: AppState, now: datetime) -> WeekSummary:
    tz = _tz(state)
    week_start, week_end = week_bounds(now, tz)
    settings = state.settings
    goal = settings.weekly_exercise_goal_hours
    session_min = settings.session_min_hours
    session_max = settings.session_max_hours

    completed = 0.0
    planned = 0.0
    walking_hours = 0.0
    exercise_events = [
        e
        for e in state.events
        if e.type == EventType.EXERCISE
        and e.start < week_end
        and e.end > week_start
    ]
    for e in exercise_events:
        h = hours_between(max(e.start, week_start), min(e.end, week_end))
        if e.activity == Activity.WALKING:
            walking_hours += h
        if e.completed or e.end <= now:
            completed += h
        else:
            planned += h

    remaining = max(0.0, goal - completed - planned)

    # Feasible days / max possible in free windows from now to week end
    feasible_days = 0
    max_possible = 0.0
    day = max(_as_local(now, tz), week_start)
    # Snap to start of current local day hour for window search: use now as floor
    while day.date() < week_end.date() or (
        day.date() == (week_end - timedelta(seconds=1)).date()
        and day < week_end
    ):
        local_day = day.date() if day.tzinfo else _as_local(day, tz).date()
        day_start = datetime(
            local_day.year, local_day.month, local_day.day, 6, 0, tzinfo=tz
        )
        day_end = datetime(
            local_day.year, local_day.month, local_day.day, 22, 0, tzinfo=tz
        )
        if day_end <= now:
            day = day_start + timedelta(days=1)
            continue
        window_start = max(day_start, now)
        windows = free_windows_for_day(
            window_start, day_end, state.events, session_min
        )
        day_capacity = 0.0
        for w_start, w_end in windows:
            day_capacity += min(session_max, hours_between(w_start, w_end))
        # Cap by walking max remaining if only walking — capacity is general
        if day_capacity >= session_min:
            feasible_days += 1
            max_possible += day_capacity
        day = day_start + timedelta(days=1)
        if day >= week_end:
            break

    if settings.walking_max_hours is not None:
        # Capacity not further reduced here for mixed activities; walking
        # suggestions respect the cap separately.
        pass

    # Sessions needed uses session max (ceil)
    if remaining <= 0:
        sessions_needed = 0
    else:
        sessions_needed = int(math.ceil(remaining / session_max))

    feasible = remaining <= max_possible + 1e-6

    return WeekSummary(
        completed_hours=round(completed, 2),
        planned_hours=round(planned, 2),
        remaining_hours=round(remaining, 2),
        sessions_needed=sessions_needed,
        feasible_days=feasible_days,
        feasible=feasible,
        max_possible_hours=round(max_possible, 2),
        goal_hours=goal,
    )


def _dismissal_blocks(
    state: AppState, rule_id: str, fingerprint: str
) -> bool:
    for d in state.dismissals:
        if d.rule_id != rule_id:
            continue
        if d.mode == "suppress":
            return True
        if d.mode == "ignore" and d.condition_fingerprint == fingerprint:
            return True
    return False


def _protein_rich_recipes(state: AppState) -> list:
    recipes = sorted(state.recipes, key=lambda r: r.protein_g, reverse=True)
    return recipes


def evaluate_rules(state: AppState, now: datetime, summary: WeekSummary) -> tuple[list[Suggestion], list[Suggestion]]:
    tz = _tz(state)
    suggestions: list[Suggestion] = []
    warnings: list[Suggestion] = []
    settings = state.settings
    week_start, week_end = week_bounds(now, tz)
    today_local = _as_local(now, tz).date()
    day_start = datetime(
        today_local.year, today_local.month, today_local.day, tzinfo=tz
    )
    day_end = day_start + timedelta(days=1)

    enabled = [r for r in state.rules if r.enabled]
    enabled.sort(key=lambda r: (-r.priority, 0 if r.strength.value == "mandatory" else 1))

    exercise_today = [
        e
        for e in state.events
        if e.type == EventType.EXERCISE and overlaps(e.start, e.end, day_start, day_end)
    ]
    sporting_today = [
        e
        for e in state.events
        if e.type == EventType.SPORTING and overlaps(e.start, e.end, day_start, day_end)
    ]
    exercise_hours_today = sum(hours_between(e.start, e.end) for e in exercise_today)
    sporting_hours_today = sum(hours_between(e.start, e.end) for e in sporting_today)
    cycling_hours_today = sum(
        hours_between(e.start, e.end)
        for e in exercise_today
        if e.activity == Activity.CYCLING
    )

    walking_week = sum(
        hours_between(e.start, e.end)
        for e in state.events
        if e.type == EventType.EXERCISE
        and e.activity == Activity.WALKING
        and overlaps(e.start, e.end, week_start, week_end)
    )

    for rule in enabled:
        if rule.condition_key == "session_too_short":
            for e in state.events:
                if e.type != EventType.EXERCISE:
                    continue
                h = hours_between(e.start, e.end)
                if h < settings.session_min_hours:
                    fp = f"short:{e.id}"
                    if _dismissal_blocks(state, rule.id, fp):
                        continue
                    warnings.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.WARNING,
                            explanation=rule.explanation,
                            title=f"{e.title} is under the session minimum",
                            proposed={"event_id": e.id, "hours": h},
                            actions=["accept", "modify"]
                            if not rule.overridable
                            else ["accept", "modify", "ignore", "suppress"],
                        )
                    )

        elif rule.condition_key == "session_too_long":
            for e in state.events:
                if e.type != EventType.EXERCISE:
                    continue
                h = hours_between(e.start, e.end)
                if h > settings.session_max_hours:
                    fp = f"long:{e.id}"
                    if _dismissal_blocks(state, rule.id, fp):
                        continue
                    warnings.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.WARNING,
                            explanation=rule.explanation,
                            title=f"{e.title} exceeds the session maximum",
                            proposed={"event_id": e.id, "hours": h},
                            actions=["accept", "modify"]
                            if not rule.overridable
                            else ["accept", "modify", "ignore", "suppress"],
                        )
                    )

        elif rule.condition_key == "walking_over_cap":
            cap = settings.walking_max_hours
            if cap is not None and walking_week > cap:
                fp = f"walk:{week_start.date()}:{walking_week}"
                if not _dismissal_blocks(state, rule.id, fp):
                    warnings.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.WARNING,
                            explanation=rule.explanation,
                            title=f"Walking {walking_week:.1f}h exceeds cap {cap}h",
                            proposed={"walking_hours": walking_week},
                            actions=["accept", "modify"],
                        )
                    )

        elif rule.condition_key == "exercise_below_goal":
            if (
                summary.remaining_hours > 0
                and summary.feasible_days >= 1
            ):
                fp = f"goal:{week_start.date()}:{summary.remaining_hours}"
                if _dismissal_blocks(state, rule.id, fp):
                    continue
                # Propose sessions that close the gap
                gap = summary.remaining_hours
                if 0 < gap < settings.session_min_hours:
                    duration = settings.session_min_hours
                else:
                    duration = min(settings.session_max_hours, max(settings.session_min_hours, gap))
                # Find a free window
                proposed_start = None
                proposed_end = None
                day = max(_as_local(now, tz), week_start)
                while day < week_end and proposed_start is None:
                    local_day = _as_local(day, tz).date()
                    ds = datetime(local_day.year, local_day.month, local_day.day, 6, 0, tzinfo=tz)
                    de = datetime(local_day.year, local_day.month, local_day.day, 22, 0, tzinfo=tz)
                    if de <= now:
                        day = ds + timedelta(days=1)
                        continue
                    for w_start, w_end in free_windows_for_day(
                        max(ds, now), de, state.events, settings.session_min_hours
                    ):
                        slot_end = w_start + timedelta(hours=duration)
                        if slot_end <= w_end:
                            proposed_start = w_start
                            proposed_end = slot_end
                            break
                    day = ds + timedelta(days=1)

                if proposed_start is not None:
                    for activity in (Activity.CYCLING, Activity.GYM, Activity.WALKING):
                        if (
                            activity == Activity.WALKING
                            and settings.walking_max_hours is not None
                            and walking_week + duration > settings.walking_max_hours
                        ):
                            continue
                        suggestions.append(
                            Suggestion(
                                rule_id=rule.id,
                                kind=SuggestionKind.EXERCISE,
                                explanation=(
                                    f"{rule.explanation} "
                                    f"Remaining {summary.remaining_hours:.1f}h toward "
                                    f"{summary.goal_hours:.0f}h goal."
                                ),
                                title=f"{activity.value.title()} — {duration:.1f}h",
                                proposed={
                                    "type": "exercise",
                                    "title": activity.value.title(),
                                    "activity": activity.value,
                                    "start": proposed_start.isoformat(),
                                    "end": proposed_end.isoformat(),
                                    "fingerprint": fp,
                                },
                            )
                        )
                        break  # one placement slot; prefer cycling

        elif rule.condition_key == "sport_below_threshold":
            if sporting_hours_today < settings.activity_threshold_hours:
                fp = f"sport_low:{today_local}"
                if _dismissal_blocks(state, rule.id, fp):
                    continue
                rich = _protein_rich_recipes(state)
                if rich:
                    suggestions.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.MEAL,
                            explanation=rule.explanation,
                            title=f"Protein-rich: {rich[0].name}",
                            proposed={
                                "type": "meal",
                                "recipe_id": rich[0].id,
                                "title": rich[0].name,
                                "fingerprint": fp,
                            },
                        )
                    )

        elif rule.condition_key == "exercise_below_threshold":
            if exercise_hours_today < settings.activity_threshold_hours:
                fp = f"ex_low:{today_local}"
                if _dismissal_blocks(state, rule.id, fp):
                    continue
                rich = _protein_rich_recipes(state)
                if rich:
                    suggestions.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.MEAL,
                            explanation=rule.explanation,
                            title=f"Protein-rich: {rich[0].name}",
                            proposed={
                                "type": "meal",
                                "recipe_id": rich[0].id,
                                "title": rich[0].name,
                                "fingerprint": fp,
                            },
                        )
                    )

        elif rule.condition_key == "exercise_at_threshold":
            if (
                exercise_hours_today >= settings.activity_threshold_hours
                and settings.protein_target_g is not None
            ):
                fp = f"ex_hi:{today_local}"
                if _dismissal_blocks(state, rule.id, fp):
                    continue
                matches = [
                    r
                    for r in state.recipes
                    if r.protein_g >= settings.protein_target_g
                ]
                if matches:
                    suggestions.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.MEAL,
                            explanation=(
                                f"{rule.explanation} Protein target "
                                f"{settings.protein_target_g}g."
                            ),
                            title=matches[0].name,
                            proposed={
                                "type": "meal",
                                "recipe_id": matches[0].id,
                                "title": matches[0].name,
                                "fingerprint": fp,
                            },
                        )
                    )

        elif rule.condition_key == "cycling_at_threshold":
            if (
                cycling_hours_today >= settings.activity_threshold_hours
                and settings.protein_target_g is not None
                and settings.carbohydrate_target_g is not None
            ):
                fp = f"cyc_hi:{today_local}"
                if _dismissal_blocks(state, rule.id, fp):
                    continue
                matches = [
                    r
                    for r in state.recipes
                    if r.protein_g >= settings.protein_target_g
                    and r.carbohydrates_g >= settings.carbohydrate_target_g
                ]
                if matches:
                    suggestions.append(
                        Suggestion(
                            rule_id=rule.id,
                            kind=SuggestionKind.MEAL,
                            explanation=rule.explanation,
                            title=matches[0].name,
                            proposed={
                                "type": "meal",
                                "recipe_id": matches[0].id,
                                "title": matches[0].name,
                                "fingerprint": fp,
                            },
                        )
                    )

        elif rule.condition_key == "stock_at_or_below_min":
            # Handled after shopping recompute via warnings for low projected stock
            pass

    return suggestions, warnings


def recompute_shopping_and_reminders(
    state: AppState, now: datetime
) -> tuple[list[ShoppingLine], list[Event], list[Suggestion]]:
    tz = _tz(state)
    settings = state.settings
    today = _as_local(now, tz).date()
    recipes = {r.id: r for r in state.recipes}
    inv_by_name = {i.name.lower(): i for i in state.fridge}

    demand: dict[str, float] = defaultdict(float)
    demand_unit: dict[str, Unit] = {}
    meal_timeline: list[tuple[datetime, dict[str, float]]] = []

    for e in sorted(
        [ev for ev in state.events if ev.type == EventType.MEAL and not ev.eaten],
        key=lambda x: x.start,
    ):
        recipe = recipes.get(e.recipe_id or "")
        if not recipe:
            continue
        meal_demand: dict[str, float] = defaultdict(float)
        for line in recipe.ingredients:
            key = line.name
            qty = line.quantity * e.portions
            demand[key] += qty
            demand_unit[key] = line.unit
            meal_demand[key] += qty
        meal_timeline.append((e.start, dict(meal_demand)))

    checked = [s for s in state.shopping if s.checked]
    checked_names = {s.ingredient.lower() for s in checked}
    new_lines: list[ShoppingLine] = list(checked)

    for name, required in demand.items():
        item = inv_by_name.get(name.lower())
        available = available_qty(item, today) if item else 0.0
        minimum = item.minimum_quantity if item else 0.0
        replenish = item.replenishment_quantity if item else 0.0
        unit = demand_unit.get(name, Unit.G)
        qty = purchase_quantity(required, available, minimum, replenish)
        if qty > 0 and name.lower() not in checked_names:
            new_lines.append(
                ShoppingLine(
                    ingredient=name,
                    quantity=qty,
                    unit=unit,
                    checked=False,
                )
            )

    # Earliest day each ingredient would hit the minimum (from meal plan).
    stock = {
        name: available_qty(item, today) for name, item in inv_by_name.items()
    }
    for name in demand:
        stock.setdefault(name.lower(), 0.0)

    runout_day: dict[str, date] = {}
    for meal_start, meal_demand in meal_timeline:
        for name, qty in meal_demand.items():
            key = name.lower()
            before = stock.get(key, 0.0)
            after = before - qty
            item = inv_by_name.get(key)
            min_q = item.minimum_quantity if item else 0.0
            if before > min_q and after <= min_q and key not in runout_day:
                runout_day[key] = _as_local(meal_start, tz).date()
            stock[key] = after

    # Open lines with the day they must be bought by (need day).
    pending: list[tuple[date, str, float, Unit]] = []
    for line in new_lines:
        if line.checked:
            continue
        key = line.ingredient.lower()
        need = runout_day.get(key, today)
        if need < today:
            need = today
        pending.append((need, line.ingredient, line.quantity, line.unit))

    shopping_days: dict[date, list[tuple[str, float, Unit]]] = defaultdict(list)
    batch = _action_enabled(state, "batch_shopping")
    if batch and pending:
        lead = max(0, state.settings.shopping_lead_days)
        batch_days = max(1, state.settings.shopping_batch_days)
        remaining = sorted(pending, key=lambda row: (row[0], row[1].lower()))
        while remaining:
            first_need = remaining[0][0]
            trip_day = first_need - timedelta(days=lead)
            if trip_day < today:
                trip_day = today
            cover_until = trip_day + timedelta(days=batch_days)
            covered: list[tuple[date, str, float, Unit]] = []
            leftover: list[tuple[date, str, float, Unit]] = []
            for row in remaining:
                # Include anything already due, or needed before the next batch window.
                if row[0] < cover_until:
                    covered.append(row)
                else:
                    leftover.append(row)
            if not covered:
                covered = [remaining[0]]
                leftover = remaining[1:]
            for _need, name, qty, unit in covered:
                shopping_days[trip_day].append((name, qty, unit))
            remaining = leftover
    else:
        for need, name, qty, unit in pending:
            shopping_days[need].append((name, qty, unit))

    # Remove old auto shopping reminders; keep user ones
    kept_events = [
        e
        for e in state.events
        if not (e.type == EventType.SHOPPING and e.origin == Origin.AUTO)
    ]
    shop_duration = timedelta(minutes=max(15, settings.shopping_duration_min))
    earliest = max(0, min(23, settings.exercise_earliest_hour))
    for day, items in sorted(shopping_days.items()):
        parts = [f"{n} {q:g}{u.value}" for n, q, u in items]
        title = "Shopping — " + ", ".join(parts)
        if len(title) > 80:
            title = f"Shopping — {len(items)} items"
        # Prefer a free timed slot outside work (evening, or weekend morning).
        preferred_hour = 10 if day.weekday() >= 5 else 17
        preferred = datetime(day.year, day.month, day.day, preferred_hour, 0, tzinfo=tz)
        search_start = datetime(day.year, day.month, day.day, earliest, 0, tzinfo=tz)
        search_end = datetime(day.year, day.month, day.day, 22, 0, tzinfo=tz)
        slot = find_non_overlapping_slot(
            preferred, shop_duration, kept_events, search_start, search_end
        )
        if slot is None:
            # Try following days for a free shopping window.
            for offset in range(1, 8):
                alt = day + timedelta(days=offset)
                preferred = datetime(
                    alt.year, alt.month, alt.day,
                    10 if alt.weekday() >= 5 else 17, 0, tzinfo=tz,
                )
                search_start = datetime(
                    alt.year, alt.month, alt.day, earliest, 0, tzinfo=tz
                )
                search_end = datetime(alt.year, alt.month, alt.day, 22, 0, tzinfo=tz)
                slot = find_non_overlapping_slot(
                    preferred, shop_duration, kept_events, search_start, search_end
                )
                if slot is not None:
                    break
        if slot is None:
            continue
        start, end = slot
        kept_events.append(
            Event(
                id=new_id(),
                title=title,
                type=EventType.SHOPPING,
                start=start,
                end=end,
                all_day=False,
                origin=Origin.AUTO,
                ingredient_name=items[0][0] if len(items) == 1 else None,
            )
        )

    return new_lines, kept_events, []


ROUTINE_WORK_TITLE = "Work"


def _action_enabled(state: AppState, action_key: str) -> bool:
    """True when an enabled rule with this action exists, or no such rule is defined yet."""
    matching = [r for r in state.rules if r.action_key == action_key]
    if not matching:
        return True
    return any(r.enabled for r in matching)


def _is_routine_event(e: Event) -> bool:
    if e.origin != Origin.AUTO:
        return False
    if e.type == EventType.PERSONAL and e.title == ROUTINE_WORK_TITLE:
        return True
    # Auto meal slots are rebuilt each recalculation (user overrides keep origin=user).
    if e.type == EventType.MEAL:
        return True
    return False


def _pick_recipe(state: AppState, meal_type: str) -> str | None:
    typed = [r for r in state.recipes if r.meal_type.lower() == meal_type]
    if typed:
        return typed[0].id
    return state.recipes[0].id if state.recipes else None


def _user_meal_covers_slot(
    events: list[Event],
    local_date: date,
    hour: int,
    tz: ZoneInfo | timezone,
) -> bool:
    """True when the user already placed a meal on this day for this slot hour."""
    for e in events:
        if e.type != EventType.MEAL or e.origin != Origin.USER:
            continue
        local = _as_local(e.start, tz)
        if local.date() == local_date and local.hour == hour:
            return True
    return False


def _user_work_on_day(
    events: list[Event], local_date: date, tz: ZoneInfo | timezone
) -> bool:
    for e in events:
        if e.origin != Origin.USER:
            continue
        if e.type == EventType.PERSONAL and e.title == ROUTINE_WORK_TITLE:
            if _as_local(e.start, tz).date() == local_date:
                return True
    return False


def apply_work_and_meals(state: AppState, now: datetime) -> AppState:
    """Upsert auto work blocks and breakfast/lunch/dinner for the current week.

    Work hours are placed in full (split around lunch). Meals and later exercise
    must fit free windows — work is never shrunk to make room for exercise.
    """
    tz = _tz(state)
    week_start, week_end = week_bounds(now, tz)
    settings = state.settings
    state = state.model_copy(deep=True)
    state.events = [e for e in state.events if not _is_routine_event(e)]

    place_work = _action_enabled(state, "place_work_blocks")
    place_meals = _action_enabled(state, "place_daily_meals")
    if not place_work and not place_meals:
        return state

    earliest = max(0, min(23, settings.exercise_earliest_hour))
    day = week_start
    while day < week_end:
        local_date = _as_local(day, tz).date()
        weekday = local_date.weekday()
        day_search_start = datetime(
            local_date.year, local_date.month, local_date.day, earliest, 0, tzinfo=tz
        )
        day_search_end = datetime(
            local_date.year, local_date.month, local_date.day, 22, 0, tzinfo=tz
        )
        lunch_start, lunch_end = _lunch_break_bounds(local_date, settings, tz)

        # Full work blocks first (mandatory schedule).
        if place_work and not _user_work_on_day(state.events, local_date, tz):
            for block in settings.work_blocks:
                if block.weekday != weekday:
                    continue
                start_h = int(block.start_hour)
                start_m = int(round((block.start_hour - start_h) * 60))
                end_h = int(block.end_hour)
                end_m = int(round((block.end_hour - end_h) * 60))
                block_start = datetime(
                    local_date.year, local_date.month, local_date.day,
                    start_h, start_m, tzinfo=tz,
                )
                block_end = datetime(
                    local_date.year, local_date.month, local_date.day,
                    end_h, end_m, tzinfo=tz,
                )
                for seg_start, seg_end in _work_segments_around_lunch(
                    block_start, block_end, lunch_start, lunch_end
                ):
                    state.events.append(
                        Event(
                            title=ROUTINE_WORK_TITLE,
                            type=EventType.PERSONAL,
                            start=seg_start,
                            end=seg_end,
                            origin=Origin.AUTO,
                        )
                    )

        if place_meals:
            meal_slots = [
                ("Breakfast", settings.breakfast_hour, "breakfast", settings.meal_duration_min),
                ("Lunch", settings.lunch_hour, "lunch", settings.lunch_duration_min),
                ("Dinner", settings.dinner_hour, "dinner", settings.meal_duration_min),
            ]
            for title, hour, meal_type, duration_min in meal_slots:
                if _user_meal_covers_slot(state.events, local_date, hour, tz):
                    continue
                recipe_id = _pick_recipe(state, meal_type)
                if not recipe_id and meal_type == "lunch":
                    recipe_id = _pick_recipe(state, "dinner")
                if not recipe_id:
                    continue
                recipe = next((r for r in state.recipes if r.id == recipe_id), None)
                preferred = datetime(
                    local_date.year, local_date.month, local_date.day,
                    hour, 0, tzinfo=tz,
                )
                slot = find_non_overlapping_slot(
                    preferred,
                    timedelta(minutes=duration_min),
                    state.events,
                    day_search_start,
                    day_search_end,
                )
                if slot is None:
                    continue
                start, end = slot
                state.events.append(
                    Event(
                        title=recipe.name if recipe else title,
                        type=EventType.MEAL,
                        start=start,
                        end=end,
                        origin=Origin.AUTO,
                        recipe_id=recipe_id,
                        portions=1.0,
                    )
                )

        day = day + timedelta(days=1)

    return state


def _exercise_count_on_date(
    events: list[Event], day: date, tz: ZoneInfo | timezone
) -> int:
    return sum(
        1
        for e in events
        if e.type == EventType.EXERCISE and _as_local(e.start, tz).date() == day
    )


def _dedupe_identical_events(events: list[Event]) -> list[Event]:
    seen: set[tuple] = set()
    out: list[Event] = []
    for e in events:
        key = (
            e.type,
            e.start.isoformat(),
            e.end.isoformat(),
            e.title,
            e.recipe_id,
            e.activity,
            e.origin,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _candidate_exercise_days(
    week_start: datetime, week_end: datetime, tz: ZoneInfo | timezone, now: datetime
) -> list[date]:
    """Weekends first, then weekdays — use Sat/Sun for volume."""
    days: list[date] = []
    d = _as_local(week_start, tz).date()
    end = _as_local(week_end - timedelta(seconds=1), tz).date()
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    today = _as_local(now, tz).date()
    days = [x for x in days if x >= today]
    weekends = [x for x in days if x.weekday() >= 5]
    weekdays = [x for x in days if x.weekday() < 5]
    return weekends + weekdays


def repair_exercise_events(state: AppState, now: datetime) -> AppState:
    """Move exercise out of work/meals; enforce ≤1 block per weekday."""
    tz = _tz(state)
    settings = state.settings
    earliest = max(0, min(23, settings.exercise_earliest_hour))
    week_start, week_end = week_bounds(now, tz)
    state = state.model_copy(deep=True)

    others = [e for e in state.events if e.type != EventType.EXERCISE]
    exercises = sorted(
        [e for e in state.events if e.type == EventType.EXERCISE],
        key=lambda e: (e.start, e.id),
    )
    placed: list[Event] = list(others)
    weekday_counts: dict[date, int] = defaultdict(int)

    for ex in exercises:
        duration = ex.end - ex.start
        if duration.total_seconds() <= 0:
            continue
        local = _as_local(ex.start, tz)
        local_day = local.date()
        is_weekday = local_day.weekday() < 5
        day_start = datetime(
            local_day.year, local_day.month, local_day.day, earliest, 0, tzinfo=tz
        )
        day_end = datetime(
            local_day.year, local_day.month, local_day.day, 22, 0, tzinfo=tz
        )
        fits_here = (
            ex.start >= day_start
            and ex.end <= day_end
            and not _timed_events_overlap_slot(placed, ex.start, ex.end)
            and not (is_weekday and weekday_counts[local_day] >= settings.max_exercise_blocks_weekday)
        )
        if fits_here:
            placed.append(ex)
            if is_weekday:
                weekday_counts[local_day] += 1
            continue

        # Reschedule into a free slot; prefer weekends for overflow.
        new_slot = None
        for day in _candidate_exercise_days(week_start, week_end, tz, now):
            if (
                day.weekday() < 5
                and weekday_counts[day] >= settings.max_exercise_blocks_weekday
            ):
                continue
            ds = datetime(day.year, day.month, day.day, earliest, 0, tzinfo=tz)
            de = datetime(day.year, day.month, day.day, 22, 0, tzinfo=tz)
            floor = max(ds, now) if day == _as_local(now, tz).date() else ds
            preferred = max(floor, ds.replace(hour=max(earliest, 17)))
            if day.weekday() >= 5:
                preferred = max(floor, ds.replace(hour=max(earliest, 9)))
            slot = find_non_overlapping_slot(
                preferred, duration, placed, floor, de
            )
            if slot is None:
                slot = find_non_overlapping_slot(
                    floor, duration, placed, floor, de
                )
            if slot is not None:
                new_slot = (day, slot)
                break
        if new_slot is None:
            # Cannot place without overlap — drop from plan rather than violate.
            continue
        day, (start, end) = new_slot
        moved = ex.model_copy(
            update={"start": start, "end": end, "origin": Origin.USER, "conflict": False}
        )
        placed.append(moved)
        if day.weekday() < 5:
            weekday_counts[day] += 1

    state.events = placed
    return state


def place_auto_exercise(state: AppState, now: datetime) -> AppState:
    """Fill toward weekly goal: weekends first, ≤1 block Mon–Fri, from 07:00."""
    state = state.model_copy(deep=True)
    state.events = [
        e
        for e in state.events
        if not (e.type == EventType.EXERCISE and e.origin == Origin.AUTO)
    ]
    if not _action_enabled(state, "spread_exercise"):
        return state

    tz = _tz(state)
    settings = state.settings
    earliest = max(0, min(23, settings.exercise_earliest_hour))
    week_start, week_end = week_bounds(now, tz)
    summary = compute_week_summary(state, now)
    remaining = summary.remaining_hours
    walking_week = sum(
        hours_between(e.start, e.end)
        for e in state.events
        if e.type == EventType.EXERCISE
        and e.activity == Activity.WALKING
        and overlaps(e.start, e.end, week_start, week_end)
    )

    for local_day in _candidate_exercise_days(week_start, week_end, tz, now):
        if remaining <= 1e-6:
            break
        is_weekday = local_day.weekday() < 5
        if is_weekday and _exercise_count_on_date(
            state.events, local_day, tz
        ) >= settings.max_exercise_blocks_weekday:
            continue

        ds = datetime(
            local_day.year, local_day.month, local_day.day, earliest, 0, tzinfo=tz
        )
        de = datetime(local_day.year, local_day.month, local_day.day, 22, 0, tzinfo=tz)
        if de <= now:
            continue
        floor = max(ds, now)
        duration = min(
            settings.session_max_hours,
            max(settings.session_min_hours, remaining)
            if remaining >= settings.session_min_hours
            else settings.session_min_hours,
        )
        preferred = floor
        if local_day.weekday() >= 5:
            preferred = max(floor, ds.replace(hour=max(earliest, 9)))
        else:
            preferred = max(floor, ds.replace(hour=max(earliest, 17)))
        slot = find_non_overlapping_slot(
            preferred,
            timedelta(hours=duration),
            state.events,
            floor,
            de,
        )
        if slot is None and duration > settings.session_min_hours:
            duration = settings.session_min_hours
            slot = find_non_overlapping_slot(
                preferred,
                timedelta(hours=duration),
                state.events,
                floor,
                de,
            )
        if slot is None:
            continue
        w_start, slot_end = slot
        activity = Activity.CYCLING
        if (
            settings.walking_max_hours is not None
            and walking_week + duration > settings.walking_max_hours
        ):
            activity = Activity.GYM
        state.events.append(
            Event(
                title=activity.value.title(),
                type=EventType.EXERCISE,
                start=w_start,
                end=slot_end,
                origin=Origin.AUTO,
                activity=activity,
            )
        )
        remaining = max(0.0, remaining - duration)
        if activity == Activity.WALKING:
            walking_week += duration

    return state


def recalculate(state: AppState, now: datetime | None = None) -> AppState:
    """Run full recalculation; returns a new AppState."""
    now = now or datetime.now(timezone.utc)
    state = state.model_copy(deep=True)
    state.events = _dedupe_identical_events(state.events)
    state = apply_work_and_meals(state, now)
    state = repair_exercise_events(state, now)
    state = place_auto_exercise(state, now)
    events = mark_conflicts(state.events)
    interim = state.model_copy(deep=True)
    interim.events = events

    shopping, events_with_reminders, stock_warnings = recompute_shopping_and_reminders(
        interim, now
    )
    interim.events = mark_conflicts(events_with_reminders)
    # After shopping placement, repair any leftover timed overlaps once more.
    interim.events = [
        e
        for e in interim.events
        if not (e.type == EventType.EXERCISE and e.origin == Origin.AUTO)
    ]
    interim = repair_exercise_events(interim, now)
    interim = place_auto_exercise(interim, now)
    interim.events = mark_conflicts(interim.events)
    interim.shopping = shopping

    summary = compute_week_summary(interim, now)
    suggestions, warnings = evaluate_rules(interim, now, summary)
    warnings = warnings + stock_warnings

    interim.week_summary = summary
    interim.suggestions = suggestions
    interim.warnings = warnings
    return interim


def to_snapshot(state: AppState) -> PlanSnapshot:
    return PlanSnapshot(
        events=state.events,
        recipes=state.recipes,
        fridge=state.fridge,
        rules=state.rules,
        shopping=state.shopping,
        settings=state.settings,
        week_summary=state.week_summary,
        suggestions=state.suggestions,
        warnings=state.warnings,
    )


def rebuild_auto_blocks(state: AppState, now: datetime | None = None) -> AppState:
    """Remove auto exercise/routine events, then recalculate to refill them.

    Args:
        state: Current app state (copied before mutation).
        now: Instant used for week bounds and scheduling; defaults to UTC now.

    Returns:
        State with auto blocks cleared and a fresh recalculation applied.
        User-origin events are preserved.
    """
    now = now or datetime.now(timezone.utc)
    state = state.model_copy(deep=True)
    state.events = [
        e
        for e in state.events
        if not (
            (e.type == EventType.EXERCISE and e.origin == Origin.AUTO)
            or _is_routine_event(e)
        )
    ]
    return recalculate(state, now)
