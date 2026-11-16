"""Database connection: URL parsing (no DB needed) + live checks (need Docker).

Live checks need: docker compose up -d
Run only those:   uv run pytest -m db
"""

from contextlib import closing

import pytest

from agent.db import connect, parse_database_url

# --- No database needed -------------------------------------------------------


def test_parse_database_url_reads_every_part():
    args = parse_database_url("postgresql://bob:s%40fe@db.example.com:6543/sales")

    assert args == {
        "user": "bob",
        "password": "s@fe",  # %40 is decoded to @
        "host": "db.example.com",
        "port": 6543,
        "database": "sales",
    }


def test_parse_database_url_rejects_wrong_scheme():
    with pytest.raises(ValueError, match="postgresql://"):
        parse_database_url("mysql://bob@localhost/sales")


# --- Needs the local Postgres container ---------------------------------------


@pytest.mark.db
def test_postgres_is_reachable_and_is_version_16():
    with closing(connect()) as conn:
        version = conn.run("SHOW server_version")[0][0]

    assert version.startswith("16"), f"expected Postgres 16, got {version}"


@pytest.mark.db
def test_pgvector_extension_is_installed():
    with closing(connect()) as conn:
        rows = conn.run("SELECT extversion FROM pg_extension WHERE extname = 'vector'")

    assert rows, "pgvector missing: run `docker compose down -v` then `docker compose up -d`"
