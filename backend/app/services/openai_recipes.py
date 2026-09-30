"""OpenAI structured-output helper for meal-library drafts."""

from __future__ import annotations

from fastapi import HTTPException
from openai import OpenAI

from app.config import settings
from app.schemas.models import RecipeCreate

_SYSTEM = """You turn a short meal description into one recipe object.
Use grams (g) or millilitres (ml) only. Estimate macros if not given.
Keep the recipe practical and complete enough to cook and shop for.
Fill every required field; use empty string or sensible defaults when unknown.
"""


def draft_recipe_from_message(message: str) -> RecipeCreate:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Meal chat is unavailable: set OPENAI_API_KEY in backend/.env",
        )
    text = message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        # openai>=1.40: chat.completions.parse
        parse = getattr(client.chat.completions, "parse", None)
        if parse is None:
            parse = client.beta.chat.completions.parse
        completion = parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": text},
            ],
            response_format=RecipeCreate,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface provider errors cleanly
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI request failed: {exc}",
        ) from exc

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise HTTPException(status_code=502, detail="Model returned no structured recipe")
    return parsed
