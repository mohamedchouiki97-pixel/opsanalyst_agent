"""Hybrid search over the TPC-H glossary + dictionary, using FAKE embeddings (free).

Fake vectors are stored under embedding_model='fake', so these tests never touch
the real OpenAI index.
"""

import pytest

from agent.search_index import build_index, search

pytestmark = pytest.mark.db


@pytest.fixture(scope="module", autouse=True)
def fake_index():
    # The module-scoped fixture runs before the function-scoped autouse conftest fixture,
    # so force fake embeddings here too.
    mp = pytest.MonkeyPatch()
    mp.setenv("EMBEDDING_PROVIDER", "fake")
    from agent.config import get_settings
    get_settings.cache_clear()
    summary = build_index("tpch")
    yield summary
    mp.undo()
    get_settings.cache_clear()


def test_index_contains_glossary_and_tables(fake_index):
    assert fake_index["model"] == "fake"
    assert fake_index["documents"] > 50
    assert fake_index["cost_usd"] == 0


def test_sales_finds_revenue():
    results = search("sales", kinds=["glossary"], dataset="tpch")

    assert results[0].title == "Revenue"  # synonym beats "Gross sales" title match
    assert results[0].exact_match


@pytest.mark.parametrize("query, expected", [
    ("AOV", "Average order value"),
    ("cogs", "Cost of goods sold"),
    ("backlog", "Open orders"),
])
def test_synonyms_find_their_term(query, expected):
    assert search(query, kinds=["glossary"], dataset="tpch")[0].title == expected


def test_question_finds_late_shipment_definitions():
    results = search("which suppliers caused the most late deliveries", dataset="tpch")
    titles = [r.title for r in results]

    assert "Late shipment" in titles or "Supplier late shipments" in titles


def test_results_show_both_ranks_for_debugging():
    top = search("revenue", kinds=["glossary"], dataset="tpch")[0]

    assert top.title == "Revenue"
    assert top.exact_match
    assert top.keyword_rank is not None
    assert top.vector_rank is not None
    assert top.payload["sql"].startswith("SUM(")


def test_same_search_twice_gives_identical_results():
    # Ties used to come back in storage order, so rebuilding the index could reorder them.
    first = search("revenue by customer", dataset="tpch", limit=10)
    second = search("revenue by customer", dataset="tpch", limit=10)

    assert [r.doc_id for r in first] == [r.doc_id for r in second]


def test_kind_filter_returns_only_tables():
    results = search("late shipments", kinds=["table"], dataset="tpch")

    assert results and all(r.kind == "table" for r in results)


def test_unbuilt_index_gives_clear_error():
    with pytest.raises(LookupError, match="build_search_index"):
        search("revenue", dataset="dataset_never_indexed")
