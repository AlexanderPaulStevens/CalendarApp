"""Farm Leuven shopping: always Wed evening + Sat morning trips."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from datetime import timezone

from app.rules import access as rules_access
from app.schemas import models
from app.services.plan import events as plan_events
from app.services.plan import params as plan_params

# Farm Leuven open hours by weekday (0=Mon … 6=Sun): (open_hour, close_hour).
FARM_HOURS: dict[int, tuple[int, int]] = {
    0: (9, 19),
    1: (9, 19),
    2: (9, 19),
    3: (9, 19),
    4: (9, 19),
    5: (9, 19),
    6: (9, 13),
}

ANCHOR_WEEKDAYS = (2, 5)  # Wednesday, Saturday


def farm_hours_for(day: date) -> tuple[int, int]:
    return FARM_HOURS.get(day.weekday(), (9, 19))


def available_qty(item: models.FridgeItem | None, today: date) -> float:
    if item is None:
        return 0.0
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


def _consume_stock_for_uses(
    uses: list[tuple[date, float]],
    stock: float,
    expiration: date | None,
) -> list[tuple[date, float]]:
    remaining: list[tuple[date, float]] = []
    on_hand = max(0.0, stock)
    for day, qty in uses:
        if expiration is not None and expiration < day:
            on_hand = 0.0
        if on_hand >= qty:
            on_hand -= qty
            continue
        need = qty - on_hand
        on_hand = 0.0
        remaining.append((day, need))
    return remaining


def _trip_duration(state: models.AppState) -> timedelta:
    shop = rules_access.rule_params(state, models.RuleKey.BATCH_SHOPPING)
    minutes = max(15, plan_params.as_int(shop, "shopping_duration_min", 45))
    return timedelta(minutes=minutes)


def _preferred_trip_start(
    day: date, duration: timedelta, zone: ZoneInfo | timezone
) -> datetime:
    open_h, close_h = farm_hours_for(day)
    if day.weekday() >= 5:
        # Weekend: as early as open.
        hour = open_h
    else:
        # Weekday: as late as possible before close.
        end = datetime(
            day.year, day.month, day.day, close_h, 0, tzinfo=zone
        )
        start = end - duration
        hour = start.hour
        minute = start.minute
        return datetime(
            day.year, day.month, day.day, hour, minute, tzinfo=zone
        )
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=zone)


def slide_trip_same_day(
    trip: models.Event,
    blocking: list[models.Event],
    zone: ZoneInfo | timezone,
) -> models.Event | None:
    """Move trip to another free Farm window the same day, or None."""
    day = plan_events.as_local(trip.start, zone).date()
    open_h, close_h = farm_hours_for(day)
    duration = trip.end - trip.start
    search_start = datetime(
        day.year, day.month, day.day, open_h, 0, tzinfo=zone
    )
    search_end = datetime(
        day.year, day.month, day.day, close_h, 0, tzinfo=zone
    )
    preferred = _preferred_trip_start(day, duration, zone)
    others = [e for e in blocking if e.id != trip.id]
    slot = plan_events.find_non_overlapping_slot(
        preferred, duration, others, search_start, search_end
    )
    if slot is None:
        return None
    return trip.model_copy(update={"start": slot[0], "end": slot[1]})


def _place_one_trip(
    state: models.AppState,
    day: date,
    duration: timedelta,
    zone: ZoneInfo | timezone,
) -> models.Event | None:
    open_h, close_h = farm_hours_for(day)
    search_start = datetime(
        day.year, day.month, day.day, open_h, 0, tzinfo=zone
    )
    search_end = datetime(
        day.year, day.month, day.day, close_h, 0, tzinfo=zone
    )
    preferred = _preferred_trip_start(day, duration, zone)
    min_hours = duration.total_seconds() / 3600.0

    # Prefer preferred edge; else latest free window (weekdays) or earliest
    # (weekends) so exercise keeps contested midday slots when possible.
    slot = None
    if not plan_events.timed_events_overlap_slot(
        state.events, preferred, preferred + duration
    ) and search_start <= preferred and preferred + duration <= search_end:
        slot = preferred, preferred + duration
    if slot is None:
        windows = plan_events.free_windows_for_day(
            search_start, search_end, state.events, min_hours
        )
        if day.weekday() >= 5:
            ordered = windows
        else:
            ordered = list(reversed(windows))
        for w_start, w_end in ordered:
            if day.weekday() >= 5:
                cand = w_start
            else:
                cand = w_end - duration
                if cand < w_start:
                    continue
            if cand + duration <= w_end and not plan_events.timed_events_overlap_slot(
                state.events, cand, cand + duration
            ):
                slot = cand, cand + duration
                break
    if slot is None:
        # Compress Auto exercise to take the preferred edge.
        without_ex = [
            e
            for e in state.events
            if not (
                e.type == models.EventType.EXERCISE
                and e.origin == models.Origin.AUTO
                and plan_events.overlaps(
                    e.start, e.end, preferred, preferred + duration
                )
            )
        ]
        # Also try with all auto exercise removed from the search day window.
        soft = [
            e
            for e in state.events
            if not (
                e.type == models.EventType.EXERCISE
                and e.origin == models.Origin.AUTO
                and plan_events.as_local(e.start, zone).date() == day
            )
        ]
        slot = plan_events.find_non_overlapping_slot(
            preferred, duration, soft, search_start, search_end
        )
        if slot is None:
            slot = plan_events.find_non_overlapping_slot(
                preferred, duration, without_ex, search_start, search_end
            )
        if slot is None:
            return None
        state.events = plan_events.compress_auto_exercise(
            state.events, slot[0], slot[1]
        )

    start, end = slot
    return models.Event(
        id=models.new_id(),
        title="Shopping — Farm Leuven",
        type=models.EventType.SHOPPING,
        start=start,
        end=end,
        all_day=False,
        origin=models.Origin.AUTO,
    )


def _anchor_dates(week_start: datetime, zone: ZoneInfo | timezone) -> list[date]:
    monday = plan_events.as_local(week_start, zone).date()
    return [monday + timedelta(days=w) for w in ANCHOR_WEEKDAYS]


def _user_shops_in_week(
    event_list: list[models.Event],
    week_start: datetime,
    week_end: datetime,
) -> list[models.Event]:
    return sorted(
        [
            e
            for e in event_list
            if e.type == models.EventType.SHOPPING
            and e.origin == models.Origin.USER
            and e.start < week_end
            and e.end > week_start
        ],
        key=lambda e: e.start,
    )


def _build_pending(
    state: models.AppState,
    now: datetime,
    zone: ZoneInfo | timezone,
) -> list[tuple[date, str, float, models.Unit]]:
    today = plan_events.as_local(now, zone).date()
    recipes = {r.id: r for r in state.recipes}
    inv_by_name = {i.name.lower(): i for i in state.fridge}
    meal_uses: dict[str, list[tuple[date, float]]] = defaultdict(list)
    demand_unit: dict[str, models.Unit] = {}
    display_name: dict[str, str] = {}

    for e in sorted(
        [ev for ev in state.events if ev.type == models.EventType.MEAL],
        key=lambda x: x.start,
    ):
        recipe = recipes.get(e.recipe_id or "")
        if not recipe:
            continue
        meal_day = plan_events.as_local(e.start, zone).date()
        for line in recipe.ingredients:
            key = line.name.lower()
            qty = line.quantity * e.portions
            meal_uses[key].append((meal_day, qty))
            demand_unit[key] = line.unit
            display_name[key] = line.name

    pending: list[tuple[date, str, float, models.Unit]] = []
    for key, uses in meal_uses.items():
        item = inv_by_name.get(key)
        available = available_qty(item, today)
        expiration = item.expiration_date if item else None
        uncovered = _consume_stock_for_uses(uses, available, expiration)
        if not uncovered:
            continue
        name = display_name[key]
        unit = demand_unit.get(key, models.Unit.G)
        for day, qty in uncovered:
            need_day = day if day >= today else today
            pending.append((need_day, name, qty, unit))
    return pending


def _split_lines(
    pending: list[tuple[date, str, float, models.Unit]],
    trip_dates: list[date],
    state: models.AppState,
) -> dict[date, list[models.ShoppingLine]]:
    """Assign need rows to trip dates by need-date / shelf life."""
    inv_by_name = {i.name.lower(): i for i in state.fridge}
    trip_dates = sorted(trip_dates)
    buckets: dict[date, list[tuple[date, str, float, models.Unit]]] = {
        d: [] for d in trip_dates
    }
    if not trip_dates:
        return {}

    for need_day, name, qty, unit in sorted(
        pending, key=lambda r: (r[0], r[1].lower())
    ):
        item = inv_by_name.get(name.lower())
        shelf = item.shelf_life_days if item else None
        # Latest trip on or before need_day that still covers shelf life.
        chosen: date | None = None
        for trip_day in trip_dates:
            if trip_day > need_day:
                break
            if shelf is not None and need_day > trip_day + timedelta(
                days=shelf
            ):
                continue
            chosen = trip_day
        if chosen is None:
            chosen = trip_dates[0]
        buckets[chosen].append((need_day, name, qty, unit))

    lines_by_trip: dict[date, list[models.ShoppingLine]] = {}
    for trip_day, rows in buckets.items():
        merged: dict[str, tuple[float, models.Unit]] = {}
        order: list[str] = []
        for _need, name, qty, unit in rows:
            if name not in merged:
                order.append(name)
                merged[name] = (qty, unit)
            else:
                prev_qty, prev_unit = merged[name]
                merged[name] = (prev_qty + qty, prev_unit)
        out: list[models.ShoppingLine] = []
        for name in order:
            qty, unit = merged[name]
            item = inv_by_name.get(name.lower())
            shelf = item.shelf_life_days if item else None
            if shelf is None and item is not None:
                qty = purchase_quantity(
                    qty,
                    0.0,
                    item.minimum_quantity,
                    item.replenishment_quantity,
                )
            out.append(
                models.ShoppingLine(
                    ingredient=name,
                    quantity=qty,
                    unit=unit,
                    trip_date=trip_day,
                )
            )
        lines_by_trip[trip_day] = out
    return lines_by_trip


def _title_for_lines(lines: list[models.ShoppingLine]) -> str:
    if not lines:
        return "Shopping — Farm Leuven"
    parts = [f"{ln.ingredient} {ln.quantity:g}{ln.unit.value}" for ln in lines]
    title = "Shopping — " + ", ".join(parts)
    if len(title) > 80:
        return f"Shopping — {len(lines)} items"
    return title


def place_trips_and_lines(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Always cover Wed+Sat shopping (User trips count); build list lines."""
    zone = plan_events.tz(state)
    week_monday = plan_events.as_local(week_start, zone).date()
    week_sunday = week_monday + timedelta(days=7)
    if not rules_access.rule_enabled(state, models.RuleKey.BATCH_SHOPPING):
        state = state.model_copy(deep=True)
        state.events = [
            e
            for e in state.events
            if not (
                e.type == models.EventType.SHOPPING
                and e.origin == models.Origin.AUTO
                and e.start < week_end
                and e.end > week_start
            )
        ]
        state.shopping = [
            ln
            for ln in state.shopping
            if ln.trip_date is None
            or not (week_monday <= ln.trip_date < week_sunday)
        ]
        return state

    state = state.model_copy(deep=True)
    duration = _trip_duration(state)

    state.events = [
        e
        for e in state.events
        if not (
            e.type == models.EventType.SHOPPING
            and e.origin == models.Origin.AUTO
            and e.start < week_end
            and e.end > week_start
        )
    ]

    anchors = _anchor_dates(week_start, zone)
    user_shops = _user_shops_in_week(state.events, week_start, week_end)
    covered: set[date] = set()
    trip_dates: list[date] = []

    # Pair each User shop to nearest unused anchor.
    remaining_anchors = list(anchors)
    for shop in user_shops:
        shop_day = plan_events.as_local(shop.start, zone).date()
        trip_dates.append(shop_day)
        if not remaining_anchors:
            continue
        nearest = min(
            remaining_anchors,
            key=lambda d: abs((d - shop_day).days),
        )
        remaining_anchors.remove(nearest)
        covered.add(nearest)

    for anchor_day in remaining_anchors:
        trip = _place_one_trip(state, anchor_day, duration, zone)
        if trip is None:
            # Try nearest other open day in the week.
            monday = plan_events.as_local(week_start, zone).date()
            for offset in range(7):
                alt = monday + timedelta(days=offset)
                if alt in covered or alt in {
                    plan_events.as_local(t.start, zone).date()
                    for t in state.events
                    if t.type == models.EventType.SHOPPING
                }:
                    continue
                trip = _place_one_trip(state, alt, duration, zone)
                if trip is not None:
                    break
        if trip is not None:
            state.events.append(trip)
            trip_dates.append(
                plan_events.as_local(trip.start, zone).date()
            )

    pending = _build_pending(state, now, zone)
    unique_trips = sorted(set(trip_dates))
    lines_by_trip = _split_lines(pending, unique_trips, state)

    new_events: list[models.Event] = []
    for e in state.events:
        if (
            e.type != models.EventType.SHOPPING
            or e.origin != models.Origin.AUTO
            or not (e.start < week_end and e.end > week_start)
        ):
            new_events.append(e)
            continue
        day = plan_events.as_local(e.start, zone).date()
        lines = lines_by_trip.get(day, [])
        new_events.append(
            e.model_copy(
                update={
                    "title": _title_for_lines(lines),
                    "ingredient_name": (
                        lines[0].ingredient if len(lines) == 1 else None
                    ),
                }
            )
        )
    state.events = new_events

    kept = [
        ln
        for ln in state.shopping
        if ln.trip_date is None
        or not (week_monday <= ln.trip_date < week_sunday)
    ]
    for day in unique_trips:
        kept.extend(lines_by_trip.get(day, []))
    state.shopping = kept
    return state


def refresh_lines(
    state: models.AppState,
    now: datetime,
    week_start: datetime,
    week_end: datetime,
) -> models.AppState:
    """Rebuild shopping lines from current meals; keep trip times fixed."""
    if not rules_access.rule_enabled(state, models.RuleKey.BATCH_SHOPPING):
        return state

    zone = plan_events.tz(state)
    state = state.model_copy(deep=True)
    pending = _build_pending(state, now, zone)

    trip_dates: list[date] = []
    for e in state.events:
        if e.type != models.EventType.SHOPPING:
            continue
        if not (e.start < week_end and e.end > week_start):
            continue
        trip_dates.append(plan_events.as_local(e.start, zone).date())
    trip_dates = sorted(set(trip_dates))
    lines_by_trip = _split_lines(pending, trip_dates, state)

    for i, e in enumerate(state.events):
        if (
            e.type != models.EventType.SHOPPING
            or e.origin != models.Origin.AUTO
            or not (e.start < week_end and e.end > week_start)
        ):
            continue
        day = plan_events.as_local(e.start, zone).date()
        lines = lines_by_trip.get(day, [])
        state.events[i] = e.model_copy(
            update={
                "title": _title_for_lines(lines),
                "ingredient_name": (
                    lines[0].ingredient if len(lines) == 1 else None
                ),
            }
        )

    week_monday = plan_events.as_local(week_start, zone).date()
    week_sunday = week_monday + timedelta(days=7)
    kept = [
        ln
        for ln in state.shopping
        if ln.trip_date is None
        or not (week_monday <= ln.trip_date < week_sunday)
    ]
    for day in trip_dates:
        kept.extend(lines_by_trip.get(day, []))
    state.shopping = kept
    return state
