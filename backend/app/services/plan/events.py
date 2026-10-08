"""Timezone, week bounds, overlap, and free-window helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings as app_config
from app.schemas import models


def tz(_state: models.AppState | None = None) -> ZoneInfo | timezone:
    del _state  # reserved for per-user timezone later
    try:
        return ZoneInfo(app_config.default_timezone)
    except Exception:
        return timezone.utc


def as_local(dt: datetime, zone: ZoneInfo | timezone) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(zone)


def week_bounds(
    ref: datetime | date,
    zone: ZoneInfo | timezone,
) -> tuple[datetime, datetime]:
    """Monday 00:00 inclusive to next Monday 00:00 exclusive."""
    if isinstance(ref, datetime):
        local = as_local(ref, zone)
        monday_date = local.date() - timedelta(days=local.weekday())
    else:
        monday_date = ref - timedelta(days=ref.weekday())
    start = datetime(
        monday_date.year, monday_date.month, monday_date.day, tzinfo=zone
    )
    return start, start + timedelta(days=7)


def event_window_for_week(
    state: models.AppState,
    anchor: date | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Monday–Sunday window containing anchor (or today when unset)."""
    zone = tz(state)
    if anchor is None:
        anchor = as_local(now, zone).date()
    return week_bounds(anchor, zone)


def hours_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600.0)


def overlaps(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    return a_start < b_end and b_start < a_end


def mark_conflicts(events: list[models.Event]) -> list[models.Event]:
    """Set ``conflict`` on timed events that overlap another timed event."""
    flags = [False] * len(events)
    timed_idx = [i for i, e in enumerate(events) if not e.all_day]
    for a, i in enumerate(timed_idx):
        ei = events[i]
        for j in timed_idx[a + 1 :]:
            ej = events[j]
            if overlaps(ei.start, ei.end, ej.start, ej.end):
                flags[i] = True
                flags[j] = True
    out: list[models.Event] = []
    for i, e in enumerate(events):
        if e.conflict == flags[i]:
            out.append(e)
        else:
            out.append(e.model_copy(update={"conflict": flags[i]}))
    return out


def clear_auto_in_week(
    events: list[models.Event],
    week_start: datetime,
    week_end: datetime,
    *,
    event_types: set[models.EventType] | None = None,
    titles: set[str] | None = None,
    predicate=None,
) -> list[models.Event]:
    """Drop Auto events overlapping the week that match filters."""

    def keep(e: models.Event) -> bool:
        if e.origin != models.Origin.AUTO:
            return True
        if not (e.start < week_end and e.end > week_start):
            return True
        if predicate is not None:
            return not predicate(e)
        if event_types is not None and e.type not in event_types:
            return True
        if titles is not None and e.title not in titles:
            return True
        if event_types is None and titles is None:
            return True
        return False

    return [e for e in events if keep(e)]


def free_windows_for_day(
    day_start: datetime,
    day_end: datetime,
    events: list[models.Event],
    min_hours: float,
) -> list[tuple[datetime, datetime]]:
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


def timed_events_overlap_slot(
    events: list[models.Event], start: datetime, end: datetime
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
    events: list[models.Event],
    search_start: datetime,
    search_end: datetime,
) -> tuple[datetime, datetime] | None:
    preferred_end = preferred_start + duration
    if (
        preferred_start >= search_start
        and preferred_end <= search_end
        and not timed_events_overlap_slot(
            events, preferred_start, preferred_end
        )
    ):
        return preferred_start, preferred_end

    min_hours = duration.total_seconds() / 3600.0
    for w_start, w_end in free_windows_for_day(
        search_start, search_end, events, min_hours
    ):
        if w_start <= preferred_start and preferred_start + duration <= w_end:
            return preferred_start, preferred_start + duration
        slot_end = w_start + duration
        if slot_end <= w_end:
            return w_start, slot_end
    return None


def dedupe_identical_events(
    events: list[models.Event],
) -> list[models.Event]:
    seen: set[tuple] = set()
    out: list[models.Event] = []
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


def compress_auto_exercise(
    events: list[models.Event],
    trip_start: datetime,
    trip_end: datetime,
) -> list[models.Event]:
    """Shorten or drop Auto exercise that overlaps ``[trip_start, trip_end)``."""
    out: list[models.Event] = []
    for e in events:
        if (
            e.type != models.EventType.EXERCISE
            or e.origin != models.Origin.AUTO
            or not overlaps(e.start, e.end, trip_start, trip_end)
        ):
            out.append(e)
            continue
        # Keep the longer non-overlapping remnant if any.
        before_end = min(e.end, trip_start)
        after_start = max(e.start, trip_end)
        kept = False
        if before_end > e.start and hours_between(e.start, before_end) >= 0.5:
            out.append(e.model_copy(update={"end": before_end}))
            kept = True
        if after_start < e.end and hours_between(after_start, e.end) >= 0.5:
            if kept:
                out.append(
                    e.model_copy(
                        update={
                            "id": models.new_id(),
                            "start": after_start,
                        }
                    )
                )
            else:
                out.append(e.model_copy(update={"start": after_start}))
            kept = True
        # else drop the session entirely
    return out
