"""Typed accessors for Rule parameter dicts."""

from __future__ import annotations

from typing import Any


def as_float(params: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = params.get(key, default)
    if val is None:
        return default
    return float(val)


def as_int(params: dict[str, Any], key: str, default: int = 0) -> int:
    val = params.get(key, default)
    if val is None:
        return default
    return int(val)
