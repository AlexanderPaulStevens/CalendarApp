from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness check; reports whether OpenAI is configured."""
    return {
        "status": "ok",
        "openai_configured": bool(settings.openai_api_key),
    }
