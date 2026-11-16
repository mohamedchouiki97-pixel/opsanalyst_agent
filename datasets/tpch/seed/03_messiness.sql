-- 03: Make clean TPC-H look like a real company's data.
-- Every change here is a deliberate trap the agent must handle (documented in the
-- dictionary/glossary so the agent CAN learn about it).

-- ---------------------------------------------------------------------------
-- Migrations log: a record of schema/data changes (used for the schema-drift
-- incident drill in Phase 7).
-- ---------------------------------------------------------------------------
CREATE TABLE tpch.migrations (
    migration_id  SERIAL PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    description   TEXT NOT NULL
);

INSERT INTO tpch.migrations (description) VALUES
    ('Initial load of TPC-H data (dates shifted +28 years: 1992-1998 -> 2020-2026)');

-- ---------------------------------------------------------------------------
-- Trap 1: test orders. QA created fake orders with huge amounts.
-- They must be excluded from every business metric (o_is_test = true).
-- We copy the first 30 orders + their line items, with new keys and inflated prices.
-- ---------------------------------------------------------------------------
ALTER TABLE tpch.orders ADD COLUMN o_is_test BOOLEAN NOT NULL DEFAULT false;

CREATE TEMP TABLE test_order_keys AS
SELECT o_orderkey AS source_key,
       (SELECT max(o_orderkey) FROM tpch.orders) + row_number() OVER (ORDER BY o_orderkey) AS new_key
FROM (SELECT o_orderkey FROM tpch.orders ORDER BY o_orderkey LIMIT 30) first_orders;

INSERT INTO tpch.orders (o_orderkey, o_custkey, o_orderstatus, o_totalprice, o_orderdate,
                         o_orderpriority, o_clerk, o_shippriority, o_comment, o_is_test)
SELECT k.new_key, o.o_custkey, o.o_orderstatus, o.o_totalprice * 50, DATE '2026-07-15',
       o.o_orderpriority, 'Clerk#QA', o.o_shippriority, 'QA TEST ORDER - DO NOT USE', true
FROM tpch.orders o
JOIN test_order_keys k ON k.source_key = o.o_orderkey;

INSERT INTO tpch.lineitem
SELECT k.new_key, l.l_partkey, l.l_suppkey, l.l_linenumber, l.l_quantity,
       l.l_extendedprice * 50, l.l_discount, l.l_tax, 'N', 'O',
       DATE '2026-07-20', DATE '2026-07-25', DATE '2026-07-30',
       l.l_shipinstruct, l.l_shipmode, 'QA test line'
FROM tpch.lineitem l
JOIN test_order_keys k ON k.source_key = l.l_orderkey;

INSERT INTO tpch.migrations (description) VALUES
    ('Added orders.o_is_test; inserted 30 QA test orders (must be excluded from metrics)');

-- ---------------------------------------------------------------------------
-- Trap 2: duplicate supplier names with different spellings.
-- Same real-world company entered several times. Grouping by s_name gives wrong
-- counts; always group by s_suppkey.
-- ---------------------------------------------------------------------------
UPDATE tpch.supplier SET s_name = 'SUPPLIER#000000010'       WHERE s_suppkey = 5010;
UPDATE tpch.supplier SET s_name = 'Supplier#000000010 '      WHERE s_suppkey = 7010;  -- trailing space
UPDATE tpch.supplier SET s_name = 'Supplier #000000020'      WHERE s_suppkey = 5020;
UPDATE tpch.supplier SET s_name = 'supplier#000000030 Inc.'  WHERE s_suppkey = 5030;

INSERT INTO tpch.migrations (description) VALUES
    ('Supplier master data import created duplicate names for suppliers 10, 20, 30');

-- ---------------------------------------------------------------------------
-- Trap 3: missing ship modes (~0.1% of line items have NULL l_shipmode).
-- ---------------------------------------------------------------------------
UPDATE tpch.lineitem SET l_shipmode = NULL WHERE l_orderkey % 1000 = 7;

INSERT INTO tpch.migrations (description) VALUES
    ('Carrier feed outage: l_shipmode is NULL for some line items');
