-- 04: Roles, permissions and row-level security (RLS).
--
-- How it fits together:
--   agent_app        LOGIN role the app connects as. Has NO permissions of its own.
--                    For each question the app runs:  SET LOCAL ROLE <user role>
--   analyst          sees all rows, no PII columns
--   europe_manager   sees only European customers (and their orders/line items), no PII
--   admin            sees everything, including PII
-- All of them can only SELECT. agent_app sessions are also read-only + 15s timeout.
--
-- Roles are cluster-wide and survive a reload, so creation is "if not exists".

-- ---------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'europe_manager') THEN
        CREATE ROLE europe_manager NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'admin') THEN
        CREATE ROLE admin NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_app') THEN
        -- Local development password only. On Azure the password lives in Key Vault.
        CREATE ROLE agent_app LOGIN PASSWORD 'agent_dev';
    END IF;
END
$$;

-- agent_app may SWITCH to these roles but does not INHERIT their permissions.
-- So if the app forgets SET ROLE, the query fails instead of running with extra access.
GRANT analyst, europe_manager, admin TO agent_app WITH INHERIT FALSE, SET TRUE;

-- Defense in depth: every agent_app session is read-only and times out after 15s.
ALTER ROLE agent_app SET default_transaction_read_only = on;
ALTER ROLE agent_app SET statement_timeout = '15s';

-- ---------------------------------------------------------------------------
-- Permissions (SELECT only, nothing else is ever granted)
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA tpch TO analyst, europe_manager, admin;

-- admin: every table and view, including PII columns
GRANT SELECT ON ALL TABLES IN SCHEMA tpch TO admin;

-- analyst + europe_manager: everything except customer PII and the migrations log
GRANT SELECT ON
    tpch.region, tpch.nation, tpch.supplier, tpch.part, tpch.partsupp,
    tpch.orders, tpch.lineitem,
    tpch.v_order_lines, tpch.v_shipments, tpch.v_customers, tpch.v_suppliers
TO analyst, europe_manager;

-- Column-level grant: every customer column EXCEPT c_phone and c_address (PII)
GRANT SELECT (c_custkey, c_name, c_nationkey, c_acctbal, c_mktsegment, c_comment)
    ON tpch.customer TO analyst, europe_manager;

-- ---------------------------------------------------------------------------
-- Row-level security
-- Each policy says which rows a role may see. A role with no policy sees nothing.
-- The orders/lineitem policies look up the (already filtered) parent table, so
-- the Europe filter flows down: customer -> orders -> lineitem.
-- ---------------------------------------------------------------------------
ALTER TABLE tpch.customer ENABLE ROW LEVEL SECURITY;
ALTER TABLE tpch.orders   ENABLE ROW LEVEL SECURITY;
ALTER TABLE tpch.lineitem ENABLE ROW LEVEL SECURITY;

CREATE POLICY all_rows ON tpch.customer FOR SELECT TO analyst, admin USING (true);
CREATE POLICY all_rows ON tpch.orders   FOR SELECT TO analyst, admin USING (true);
CREATE POLICY all_rows ON tpch.lineitem FOR SELECT TO analyst, admin USING (true);

CREATE POLICY europe_only ON tpch.customer FOR SELECT TO europe_manager
USING (
    c_nationkey IN (
        SELECT n.n_nationkey
        FROM tpch.nation n
        JOIN tpch.region r ON r.r_regionkey = n.n_regionkey
        WHERE r.r_name = 'EUROPE'
    )
);

CREATE POLICY europe_only ON tpch.orders FOR SELECT TO europe_manager
USING (EXISTS (SELECT 1 FROM tpch.customer c WHERE c.c_custkey = o_custkey));

CREATE POLICY europe_only ON tpch.lineitem FOR SELECT TO europe_manager
USING (EXISTS (SELECT 1 FROM tpch.orders o WHERE o.o_orderkey = l_orderkey));

INSERT INTO tpch.migrations (description) VALUES
    ('Created roles analyst/europe_manager/admin, PII column grants and row-level security');
