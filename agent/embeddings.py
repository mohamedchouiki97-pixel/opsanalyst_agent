"""Turn text into vectors. The ONLY file that calls an embedding API.

Providers (EMBEDDING_PROVIDER in .env):
    fake          free, deterministic, offline. Default; used by all tests.
    openai        real OpenAI API call (costs money; see DESIGN.md section 4).
    azure_openai  Phase 6.

The fake provider is a "bag of words": each word adds 1 to a slot chosen by hashing
the word. Texts that share words get similar vectors, so search tests are meaningful,
but it doesn't understand synonyms the way a real model does.
"""

import hashlib
import math
import re
from dataclasses import dataclass

from openai import OpenAI

from agent.config import get_settings


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    tokens_used: int  # 0 for the fake provider
    cost_usd: float


def index_model_name() -> str:
    """Name stored next to each vector, so vectors from different models never mix."""
    settings = get_settings()
    return "fake" if settings.embedding_provider == "fake" else settings.embedding_model


def estimate_cost_usd(texts: list[str]) -> float:
    """Rough estimate before calling the API: ~4 characters per token."""
    tokens = sum(len(t) for t in texts) / 4
    return tokens / 1_000_000 * get_settings().embedding_usd_per_1m_tokens


def embed_texts(texts: list[str]) -> EmbeddingResult:
    settings = get_settings()

    if settings.embedding_provider == "fake":
        vectors = [_fake_vector(t, settings.embedding_dimensions) for t in texts]
        return EmbeddingResult(vectors=vectors, tokens_used=0, cost_usd=0.0)

    if settings.embedding_provider == "openai":
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(model=settings.embedding_model, input=texts)
        vectors = [item.embedding for item in response.data]
        tokens = response.usage.total_tokens
        cost = tokens / 1_000_000 * settings.embedding_usd_per_1m_tokens
        return EmbeddingResult(vectors=vectors, tokens_used=tokens, cost_usd=cost)

    raise NotImplementedError(f"embedding provider '{settings.embedding_provider}' (Phase 6)")


def _fake_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % dimensions
        vector[slot] += 1.0
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]
