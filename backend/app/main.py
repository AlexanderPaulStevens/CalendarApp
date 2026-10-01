"""FastAPI application entrypoint."""

import fastapi
from fastapi.middleware import cors

from app.config import settings
from app.router.event_router import router as event_router
from app.router.fridge_router import router as fridge_router
from app.router.health_router import router as health_router
from app.router.plan_router import router as plan_router
from app.router.recipe_router import router as recipe_router
from app.router.rule_router import router as rule_router
from app.spa import mount_spa

app = fastapi.FastAPI(title="Planning Calendar")
app.add_middleware(
    cors.CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix="/api")
app.include_router(plan_router, prefix="/api")
app.include_router(event_router, prefix="/api")
app.include_router(recipe_router, prefix="/api")
app.include_router(fridge_router, prefix="/api")
app.include_router(rule_router, prefix="/api")
mount_spa(app, settings.static_dir)
