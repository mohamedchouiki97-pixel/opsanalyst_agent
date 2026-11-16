-- Business views: a friendlier layer on top of the cryptic TPC-H tables.
--
-- IMPORTANT: every view uses security_invoker = true. Without it, a view runs with
-- its OWNER's permissions and would silently bypass row-level security, so the
-- Europe manager would see every region through the view.
--
-- Views never include PII columns (c_phone, c_address).

-- One row per order line, with net revenue. Excludes QA test orders.
CREATE VIEW tpch.v_order_lines WITH (security_invoker = true) AS
SELECT
    o.o_orderkey                              AS order_key,
    l.l_linenumber                            AS line_number,
    o.o_orderdate                             AS order_date,
    o.o_orderstatus                           AS order_status,
    o.o_custkey                               AS customer_key,
    l.l_partkey                               AS part_key,
    l.l_suppkey                               AS supplier_key,
    l.l_quantity                              AS quantity,
    l.l_extendedprice                         AS gross_amount,
    l.l_discount                              AS discount,
    l.l_extendedprice * (1 - l.l_discount)    AS net_amount,
    (l.l_returnflag = 'R')                    AS is_returned,
    l.l_shipmode                              AS ship_mode
FROM tpch.lineitem l
JOIN tpch.orders o ON o.o_orderkey = l.l_orderkey
WHERE NOT o.o_is_test;

-- One row per order line with shipping dates and a late flag. Excludes QA test orders.
CREATE VIEW tpch.v_shipments WITH (security_invoker = true) AS
SELECT
    l.l_orderkey                              AS order_key,
    l.l_linenumber                            AS line_number,
    l.l_suppkey                               AS supplier_key,
    o.o_custkey                               AS customer_key,
    l.l_shipdate                              AS ship_date,
    l.l_commitdate                            AS commit_date,
    l.l_receiptdate                           AS receipt_date,
    l.l_shipmode                              AS ship_mode,
    (l.l_receiptdate > l.l_commitdate)        AS is_late,
    GREATEST(l.l_receiptdate - l.l_commitdate, 0) AS days_late
FROM tpch.lineitem l
JOIN tpch.orders o ON o.o_orderkey = l.l_orderkey
WHERE NOT o.o_is_test;

-- Customers with their nation and region names (no PII).
CREATE VIEW tpch.v_customers WITH (security_invoker = true) AS
SELECT
    c.c_custkey     AS customer_key,
    c.c_name        AS customer_name,
    c.c_mktsegment  AS market_segment,
    c.c_acctbal     AS account_balance,
    n.n_name        AS nation,
    r.r_name        AS region
FROM tpch.customer c
JOIN tpch.nation n ON n.n_nationkey = c.c_nationkey
JOIN tpch.region r ON r.r_regionkey = n.n_regionkey;

-- Suppliers with their nation and region names.
CREATE VIEW tpch.v_suppliers WITH (security_invoker = true) AS
SELECT
    s.s_suppkey     AS supplier_key,
    s.s_name        AS supplier_name,
    s.s_acctbal     AS account_balance,
    n.n_name        AS nation,
    r.r_name        AS region
FROM tpch.supplier s
JOIN tpch.nation n ON n.n_nationkey = s.s_nationkey
JOIN tpch.region r ON r.r_regionkey = n.n_regionkey;
