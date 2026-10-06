"""Closed catalog of Scheduling Rules and default parameters."""

from __future__ import annotations

from typing import Any

from app.schemas.models import (
    Rule,
    RuleKey,
    WorkBlock,
    default_study_blocks,
    default_work_blocks,
    new_id,
)


# Default parameters per rule_key (placement constraints + policy knobs).
DEFAULT_PARAMETERS: dict[RuleKey, dict[str, Any]] = {
    RuleKey.WEEKLY_EXERCISE_GOAL: {
        "goal_hours": 10.0,
        "session_min_hours": 1.0,
        "session_max_hours": 3.0,
        "exercise_earliest_hour": 7,
        "max_exercise_blocks_per_day": 1,
        "max_exercise_hours_per_day": 3.0,
        # Prefer at least this many hours on Sat+Sun when free time allows.
        "weekend_min_hours": 4.0,
        # Morning = before this hour; Mon/Thu (0/3) never get morning Auto exercise.
        "morning_end_hour": 12,
        "no_morning_weekdays": [0, 3],
        "evening_start_hour": 17,
        # Cycling Auto sessions must end by this hour; gym may run later.
        "cycling_latest_end_hour": 20,
    },
    RuleKey.DAILY_MEALS: {
        "breakfast_hour": 8,
        "lunch_hour": 12,
        "dinner_hour": 18,
        "meal_duration_min": 45,
        "lunch_duration_min": 60,
        "activity_threshold_hours": 2.0,
        "protein_target_g": None,
        "carbohydrate_target_g": None,
    },
    RuleKey.WORK_SCHEDULE: {
        "work_blocks": [
            {
                "weekday": b.weekday,
                "start_hour": b.start_hour,
                "end_hour": b.end_hour,
            }
            for b in default_work_blocks()
        ],
    },
    RuleKey.STUDY_SCHEDULE: {
        "study_blocks": [
            {
                "weekday": b.weekday,
                "start_hour": b.start_hour,
                "end_hour": b.end_hour,
            }
            for b in default_study_blocks()
        ],
        # Weekend study is free-time packed (not fixed clocks) toward this goal.
        "weekend_goal_hours": 14.0,
        "weekend_earliest_hour": 7,
        "weekend_latest_hour": 22,
        "weekend_block_min_hours": 2.0,
        "weekend_block_max_hours": 4.0,
    },
    RuleKey.BATCH_SHOPPING: {
        # ~2 store trips per week when demand is continuous (7/2 ≈ 3.5).
        "shopping_batch_days": 4,
        "shopping_lead_days": 1,
        "shopping_duration_min": 45,
        "store_open_hour": 9,
        "store_close_hour": 19,
    },
}

_CATALOG_META: dict[RuleKey, dict[str, str]] = {
    RuleKey.WEEKLY_EXERCISE_GOAL: {
        "name": "Weekly exercise goal",
        "explanation": (
            "If exercise this week is below the goal, place Auto exercise "
            "into free time — spread across as many days as possible, rotate "
            "gym/cycling, and aim for at least weekend_min_hours on "
            "Sat+Sun. One session per day within the daily hour cap. No "
            "morning sessions on Monday or Thursday; morning slots are gym "
            "only; cycling in the evening must end by 20:00."
        ),
    },
    RuleKey.DAILY_MEALS: {
        "name": "Three meals a day",
        "explanation": (
            "Place breakfast, lunch, and dinner Auto slots each day at their "
            "preferred hours — never skip a meal when another Event overlaps; "
            "conflicts are marked instead. After exercise on the calendar, "
            "swap the next Auto meal's recipe toward higher protein (or "
            "carbs+protein after cycling)."
        ),
    },
    RuleKey.WORK_SCHEDULE: {
        "name": "Working hours",
        "explanation": (
            "Place Auto work blocks for the configured weekdays and hours, "
            "split around lunch so meals do not overlap."
        ),
    },
    RuleKey.STUDY_SCHEDULE: {
        "name": "Study blocks",
        "explanation": (
            "Place Auto study blocks on weekdays from study_blocks (default "
            "Tue 09:00–12:00 and 13:00–17:00, Wed 09:00–12:00, Fri "
            "09:00–12:00). On weekends, pack free time between "
            "weekend_earliest_hour and weekend_latest_hour toward at least "
            "weekend_goal_hours (default 14)."
        ),
    },
    RuleKey.BATCH_SHOPPING: {
        "name": "Batch shopping",
        "explanation": (
            "If fridge stock cannot cover upcoming meals, place store-trip "
            "Auto events lead days before run-out — about two trips per week "
            "(batch_days of needs each), only in free time inside store open "
            "hours. Perishables (shelf_life_days on the fridge item) are only "
            "bought for meals they will still cover; pantry items may fill a "
            "full batch. A User shopping event already on the calendar covers "
            "that batch; Auto does not schedule a second trip for it."
        ),
    },
}


def default_parameters(key: RuleKey) -> dict[str, Any]:
    """Return a copy of default parameters for a catalog key."""
    raw = DEFAULT_PARAMETERS[key]
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, list):
            out[k] = [
                dict(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            out[k] = v
    return out


def build_catalog_rules() -> list[Rule]:
    """Return one Rule instance per catalog key with defaults."""
    rules: list[Rule] = []
    for key in RuleKey:
        meta = _CATALOG_META[key]
        rules.append(
            Rule(
                id=new_id(),
                rule_key=key,
                name=meta["name"],
                explanation=meta["explanation"],
                enabled=True,
                parameters=default_parameters(key),
            )
        )
    return rules


def work_blocks_from_params(params: dict[str, Any]) -> list[WorkBlock]:
    """Parse work_blocks from rule parameters."""
    return _blocks_from_params(params, "work_blocks", default_work_blocks)


def study_blocks_from_params(params: dict[str, Any]) -> list[WorkBlock]:
    """Parse study_blocks from rule parameters."""
    return _blocks_from_params(params, "study_blocks", default_study_blocks)


def _blocks_from_params(
    params: dict[str, Any],
    key: str,
    default_fn,
) -> list[WorkBlock]:
    raw = params.get(key) or []
    blocks: list[WorkBlock] = []
    for item in raw:
        if isinstance(item, WorkBlock):
            blocks.append(item)
        else:
            blocks.append(WorkBlock.model_validate(item))
    return blocks or default_fn()
