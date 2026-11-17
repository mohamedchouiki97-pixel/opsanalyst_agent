"""Dataset YAML files load, validate and reject mistakes. No database needed."""

import pytest
from pydantic import ValidationError

from agent.dataset import Glossary, load_dictionary, load_glossary


def test_tpch_dictionary_loads():
    dictionary = load_dictionary("tpch")

    assert dictionary.schema_name == "tpch"
    assert "lineitem" in dictionary.tables
    assert dictionary.tables["customer"].pii_columns == ["c_phone", "c_address"]


def test_tpch_glossary_has_40_to_60_entries():
    assert 40 <= len(load_glossary("tpch").entries) <= 60


def test_glossary_tables_exist_in_dictionary():
    tables = set(load_dictionary("tpch").tables)

    for entry in load_glossary("tpch").entries:
        unknown = set(entry.tables) - tables
        assert not unknown, f"glossary '{entry.term}' mentions unknown tables {unknown}"


def test_pii_columns_are_real_columns():
    for name, table in load_dictionary("tpch").tables.items():
        for column in table.pii_columns:
            assert column in table.columns, f"{name}.{column} marked PII but not listed"


def test_typo_in_glossary_key_is_rejected():
    with pytest.raises(ValidationError, match="synonym"):
        Glossary.model_validate(
            {"entries": [{"term": "Revenue", "definition": "x", "synonym": ["sales"]}]}
        )


def test_duplicate_glossary_terms_are_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        Glossary.model_validate({"entries": [
            {"term": "Revenue", "definition": "a"},
            {"term": "revenue", "definition": "b"},
        ]})


def test_unknown_dataset_fails_clearly():
    with pytest.raises(FileNotFoundError, match="no_such_dataset"):
        load_glossary("no_such_dataset")
