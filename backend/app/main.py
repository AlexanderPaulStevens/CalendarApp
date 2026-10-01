from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.router.event_router import router as event_router
from app.router.fridge_router import router as fridge_router
from app.router.health_router import router as health_router
from app.router.plan_router import router as plan_router
from app.router.recipe_router import router as recipe_router
from app.router.rule_router import router as rule_router
from app.router.settings_router import router as settings_router
from app.router.shopping_router import router as shopping_router
from app.router.suggestion_router import router as suggestion_router

app = FastAPI(title="Planning Calendar")
app.add_middleware(
    CORSMiddleware,
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
app.include_router(shopping_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(suggestion_router, prefix="/api")
