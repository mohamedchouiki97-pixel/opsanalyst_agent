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
    # Owner connection: setup scripts, glossary index, trace storage.
    database_url: str = "postgresql://opsanalyst:opsanalyst_dev@localhost:5432/opsanalyst"
    # Restricted connection: runs the agent's SQL (read-only, must SET ROLE first).
    agent_database_url: str = "postgresql://agent_app:agent_dev@localhost:5432/opsanalyst"

    # --- LLM ---
    # "fake" is the default so nothing costs money unless you switch it on.
    llm_provider: Literal["fake", "openai", "azure_openai"] = "fake"
    openai_api_key: str | None = None
    # Cheap model: used for every step until the Cost Autopilot router exists.
    model_cheap: str = "gpt-5.4-mini"
    # Strong model: deliberately OPEN. Chosen together with the router (DESIGN.md D2).
    model_strong: str | None = None

    # --- Embeddings (glossary/dictionary search) ---
    # "fake" is the default: free, deterministic, used by tests.
    embedding_provider: Literal["fake", "openai", "azure_openai"] = "fake"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536  # must match the vector(1536) column in the index
    embedding_usd_per_1m_tokens: float = 0.02  # verify on OpenAI's pricing page

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
    if settings.embedding_provider == "openai" and not settings.openai_api_key:
        raise ValueError("EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set in .env")

    return settings
