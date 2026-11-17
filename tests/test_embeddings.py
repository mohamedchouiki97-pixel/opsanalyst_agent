"""The fake embedder: free, deterministic, and good enough for search tests."""

import math

from agent.embeddings import embed_texts, estimate_cost_usd, index_model_name


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # vectors are unit length


def test_fake_embeddings_cost_nothing_and_have_right_size():
    result = embed_texts(["revenue by region"])

    assert result.cost_usd == 0
    assert len(result.vectors[0]) == 1536
    assert math.isclose(sum(v * v for v in result.vectors[0]), 1.0)


def test_fake_embeddings_are_deterministic():
    assert embed_texts(["late shipments"]).vectors == embed_texts(["late shipments"]).vectors


def test_texts_sharing_words_are_closer():
    a, b, c = embed_texts(["late shipments by supplier", "supplier late deliveries",
                           "customer market segment"]).vectors

    assert cosine(a, b) > cosine(a, c)


def test_index_model_name_is_fake_in_tests():
    assert index_model_name() == "fake"


def test_cost_estimate_is_tiny_for_small_text():
    assert 0 < estimate_cost_usd(["x" * 4000]) < 0.001
