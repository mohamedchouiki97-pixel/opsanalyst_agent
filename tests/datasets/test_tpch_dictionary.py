"""dictionary.yaml matches the real database (catches schema drift, Phase 7).

Needs the loaded TPC-H database.
"""

from contextlib import closing

import pytest

from agent.dataset import load_dictionary
from agent.db import connect

pytestmark = pytest.mark.db

NOT_FOR_THE_AGENT = {"migrations"}  # internal tables deliberately left undocumented


def live_columns(schema: str) -> dict[str, set[str]]:
    with closing(connect()) as conn:
        rows = conn.run(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = :schema",
            schema=schema,
        )
    columns: dict[str, set[str]] = {}
    for table, column in rows:
        columns.setdefault(table, set()).add(column)
    return columns


def test_every_documented_column_exists():
    dictionary = load_dictionary("tpch")
    live = live_columns(dictionary.schema_name)

    for table, info in dictionary.tables.items():
        assert table in live, f"dictionary mentions missing table '{table}'"
        missing = set(info.columns) - live[table]
        assert not missing, f"dictionary mentions missing columns {table}.{missing}"


def test_every_live_column_is_documented():
    dictionary = load_dictionary("tpch")
    live = live_columns(dictionary.schema_name)

    for table, columns in live.items():
        if table in NOT_FOR_THE_AGENT:
            continue
        assert table in dictionary.tables, f"table '{table}' is not in dictionary.yaml"
        undocumented = columns - set(dictionary.tables[table].columns)
        assert not undocumented, f"undocumented columns {table}.{undocumented}"
