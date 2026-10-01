from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env."""

    data_path: Path = Path("data/state.json")
    default_timezone: str = "Europe/Brussels"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Built Vite assets (set in the container). Absent locally → API-only.
    static_dir: Path | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def _normalize_openai_key(cls, value: object) -> object:
        if value in (None, "", "not-set"):
            return None
        return value


settings = Settings()
