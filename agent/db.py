"""The ONLY file that knows which Postgres driver we use (pg8000).

If we ever switch drivers, only this file changes.

Usage:
    from contextlib import closing
    from agent.db import connect

    with closing(connect()) as conn:
        rows = conn.run("SELECT 1")
"""

from urllib.parse import unquote, urlparse

import pg8000.native

from agent.config import get_settings


def parse_database_url(database_url: str) -> dict:
    """Turn 'postgresql://user:pass@host:5432/dbname' into pg8000 connect arguments."""
    url = urlparse(database_url)

    if url.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"DATABASE_URL must start with postgresql://, got '{url.scheme}://'")
    if not url.username:
        raise ValueError("DATABASE_URL is missing a user name")

    return {
        "user": unquote(url.username),
        "password": unquote(url.password) if url.password else None,
        "host": url.hostname or "localhost",
        "port": url.port or 5432,
        "database": url.path.lstrip("/") or None,
    }


def connect(database_url: str | None = None) -> pg8000.native.Connection:
    """Open a new connection. Caller must close it (use contextlib.closing)."""
    args = parse_database_url(database_url or get_settings().database_url)
    return pg8000.native.Connection(**args, timeout=10)
