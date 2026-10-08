"""Serve the built Vite SPA when STATIC_DIR is configured (production)."""

from pathlib import Path

import fastapi
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

_LOCAL_UI = "http://127.0.0.1:5173/"


def mount_spa(app: fastapi.FastAPI, static_dir: Path | None) -> None:
    """Mount hashed assets and an index.html fallback for client routes.

    When ``static_dir`` is unset (local Vite + API), ``GET /`` redirects to the
    Vite UI so opening the API port is not a confusing 404.
    """
    if static_dir is None or not static_dir.is_dir():

        @app.get("/")
        async def local_root() -> RedirectResponse:
            return RedirectResponse(url=_LOCAL_UI, status_code=307)

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
