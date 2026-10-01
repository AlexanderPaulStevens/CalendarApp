"""JSON file persistence for the single-user app state."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from threading import Lock

from app.config import settings
from app.ingredients.shelf_life import ensure_fridge_shelf_lives
from app.rules.access import ensure_catalog_rules
from app.schemas.models import AppState
from app.store.seed import build_seed_state


class JsonStore:
    """Load/save AppState to a JSON file with an in-memory cache."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings.data_path
        self._lock = Lock()
        self._state: AppState | None = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppState:
        with self._lock:
            return self._load_unlocked()

    def save(self, state: AppState) -> AppState:
        with self._lock:
            self._write_unlocked(state)
            self._state = state
            return self._state

    def mutate(self, mutator: Callable[[AppState], AppState]) -> AppState:
        with self._lock:
            state = self._load_unlocked()
            new_state = mutator(state)
            self._write_unlocked(new_state)
            self._state = new_state
            return new_state

    def _load_unlocked(self) -> AppState:
        if self._state is not None:
            return self._state
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._state = AppState.model_validate(raw)
            self._state = ensure_catalog_rules(self._state)
            self._state = ensure_fridge_shelf_lives(self._state)
        else:
            self._state = build_seed_state()
            self._write_unlocked(self._state)
        return self._state

    def _write_unlocked(self, state: AppState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )


store = JsonStore()
