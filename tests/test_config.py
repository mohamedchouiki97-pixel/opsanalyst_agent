"""Settings load with safe defaults and reject bad values."""

import pytest
from pydantic import ValidationError

from agent.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Make tests independent of the developer's real .env and shell variables."""
    for name in ["LLM_PROVIDER", "EMBEDDING_PROVIDER", "OPENAI_API_KEY", "DATASET",
                 "MAX_USD_PER_QUESTION", "MODEL_CHEAP", "MODEL_STRONG"]:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_are_safe():
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "fake"  # no money spent by default
    assert settings.model_cheap == "gpt-5.4-mini"
    assert settings.model_strong is None  # open until the router decides
    assert settings.dataset == "tpch"
    assert settings.max_usd_per_question > 0


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "opneai")  # typo on purpose

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_negative_budget_is_rejected(monkeypatch):
    monkeypatch.setenv("MAX_USD_PER_QUESTION", "-1")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_openai_without_key_fails_at_startup(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")  # overrides any key in .env

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_settings()
