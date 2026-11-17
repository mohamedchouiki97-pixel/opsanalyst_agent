"""Shared test setup.

SAFETY: every test runs with fake providers, whatever .env says.
Tests must never call a paid API (DESIGN.md rule 10).
"""

import pytest

from agent.config import get_settings


@pytest.fixture(autouse=True)
def force_fake_providers(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
