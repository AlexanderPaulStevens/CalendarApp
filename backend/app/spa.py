"""Serve the built Vite SPA when STATIC_DIR is configured (production)."""

from pathlib import Path

import fastapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: fastapi.FastAPI, static_dir: Path | None) -> None:
    """Mount hashed assets and an index.html fallback for client routes.

    No-op when ``static_dir`` is unset or missing (local Vite + API setup).
    """
    if static_dir is None or not static_dir.is_dir():
        return

    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str = "") -> FileResponse:
        if full_path:
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
