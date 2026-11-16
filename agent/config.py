"""App settings, read from environment variables and the .env file.

Settings are loaded and validated ONCE at startup. If a value is wrong
(e.g. LLM_PROVIDER=opneai), the app stops immediately with a clear error
instead of misbehaving later.

Usage:
    from agent.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # skip unrelated keys in .env (e.g. from other projects)
    )

    # --- Which dataset folder under datasets/ is active ---
    dataset: str = "tpch"

    # --- Database ---
    database_url: str = "postgresql://opsanalyst:opsanalyst_dev@localhost:5432/opsanalyst"

    # --- LLM ---
    # "fake" is the default so nothing costs money unless you switch it on.
    llm_provider: Literal["fake", "openai", "azure_openai"] = "fake"
    openai_api_key: str | None = None
    model_strong: str = "gpt-4.1"
    model_cheap: str = "gpt-4.1-mini"

    # --- Spending caps (enforced in agent/budget.py, Phase 2) ---
    max_usd_per_question: float = Field(default=0.25, gt=0)
    max_usd_per_day: float = Field(default=2.00, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Load settings once and reuse them everywhere."""
    settings = Settings()

    # Fail fast: a real provider without its key would only fail later, mid-question.
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        raise ValueError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set in .env")

    return settings
