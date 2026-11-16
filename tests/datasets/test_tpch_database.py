"""The TPC-H company database: data, messiness and security.

Needs: docker compose up -d   AND   python -m datasets.tpch.seed.load --sf 1
"""

import datetime
from contextlib import closing

import pytest
from pg8000.native import DatabaseError

from agent.config import get_settings
from agent.db import connect

pytestmark = pytest.mark.db


def query_as_owner(sql: str) -> list:
    """Query with full access (bypasses RLS). For checking the data itself."""
    with closing(connect()) as conn:
        return conn.run(sql)


def query_as(role: str, sql: str) -> list:
    """Query exactly the way the agent will: log in as agent_app, then SET LOCAL ROLE."""
    with closing(connect(get_settings().agent_database_url)) as conn:
        conn.run("BEGIN")
        try:
            conn.run(f"SET LOCAL ROLE {role}")
            return conn.run(sql)
        finally:
            conn.run("ROLLBACK")


# --- Data ----------------------------------------------------------------------


def test_row_counts_match_tpch_sf1():
    counts = query_as_owner("""
        SELECT (SELECT count(*) FROM tpch.customer),
               (SELECT count(*) FROM tpch.supplier),
               (SELECT count(*) FROM tpch.orders WHERE NOT o_is_test),
               (SELECT count(*) FROM tpch.v_order_lines)
    """)[0]

    assert counts == [150_000, 10_000, 1_500_000, 6_001_215]


def test_dates_are_shifted_to_2020_2026():
    first, last = query_as_owner(
        "SELECT min(o_orderdate), max(o_orderdate) FROM tpch.orders WHERE NOT o_is_test"
    )[0]

    assert first == datetime.date(2020, 1, 1)
    assert last == datetime.date(2026, 8, 2)


# --- Messiness -----------------------------------------------------------------


def test_test_orders_exist_but_views_exclude_them():
    test_orders = query_as_owner("SELECT count(*) FROM tpch.orders WHERE o_is_test")[0][0]
    leaked = query_as_owner("""
        SELECT count(*) FROM tpch.v_order_lines v
        JOIN tpch.orders o ON o.o_orderkey = v.order_key
        WHERE o.o_is_test
    """)[0][0]

    assert test_orders == 30
    assert leaked == 0


def test_supplier_names_have_duplicate_spellings():
    variants = query_as_owner("""
        SELECT count(*) FROM tpch.supplier
        WHERE upper(replace(trim(s_name), ' ', '')) LIKE 'SUPPLIER#000000010%'
    """)[0][0]

    assert variants == 3  # the original + 2 misspelled copies


def test_some_ship_modes_are_missing():
    null_share = query_as_owner(
        "SELECT avg((l_shipmode IS NULL)::int) FROM tpch.lineitem"
    )[0][0]

    assert 0 < null_share < 0.01


# --- Security ------------------------------------------------------------------


def test_analyst_sees_every_customer():
    assert query_as("analyst", "SELECT count(*) FROM tpch.customer")[0][0] == 150_000


def test_europe_manager_sees_only_european_customers():
    regions = query_as("europe_manager", """
        SELECT DISTINCT r.r_name
        FROM tpch.customer c
        JOIN tpch.nation n ON n.n_nationkey = c.c_nationkey
        JOIN tpch.region r ON r.r_regionkey = n.n_regionkey
    """)

    assert regions == [["EUROPE"]]


def test_europe_filter_flows_down_to_orders_and_views():
    eu_orders = query_as("europe_manager", "SELECT count(*) FROM tpch.orders")[0][0]
    all_orders = query_as("analyst", "SELECT count(*) FROM tpch.orders")[0][0]
    view_regions = query_as("europe_manager", "SELECT DISTINCT region FROM tpch.v_customers")

    assert 0 < eu_orders < all_orders
    assert view_regions == [["EUROPE"]]  # security_invoker views respect RLS


def test_analyst_cannot_read_pii():
    with pytest.raises(DatabaseError, match="permission denied"):
        query_as("analyst", "SELECT c_phone FROM tpch.customer LIMIT 1")


def test_admin_can_read_pii():
    assert query_as("admin", "SELECT c_phone FROM tpch.customer LIMIT 1")


@pytest.mark.parametrize("role", ["analyst", "europe_manager", "admin"])
def test_no_role_can_write(role):
    with pytest.raises(DatabaseError, match="read-only|permission denied"):
        query_as(role, "DELETE FROM tpch.region")


def test_agent_without_set_role_cannot_read_anything():
    with closing(connect(get_settings().agent_database_url)) as conn:
        with pytest.raises(DatabaseError, match="permission denied"):
            conn.run("SELECT * FROM tpch.region")


def test_agent_sessions_time_out_after_15_seconds():
    with closing(connect(get_settings().agent_database_url)) as conn:
        assert conn.run("SHOW statement_timeout")[0][0] == "15s"
