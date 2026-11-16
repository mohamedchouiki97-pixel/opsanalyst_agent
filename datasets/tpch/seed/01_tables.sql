-- 01: Create the 8 TPC-H tables in schema "tpch".
-- No keys or indexes yet: bulk loading is much faster without them (added in 02).
-- Column names stay cryptic on purpose: the agent must learn them from the dictionary.

CREATE TABLE tpch.region (
    r_regionkey  INTEGER NOT NULL,
    r_name       TEXT    NOT NULL,
    r_comment    TEXT
);

CREATE TABLE tpch.nation (
    n_nationkey  INTEGER NOT NULL,
    n_name       TEXT    NOT NULL,
    n_regionkey  INTEGER NOT NULL,
    n_comment    TEXT
);

CREATE TABLE tpch.supplier (
    s_suppkey    BIGINT        NOT NULL,
    s_name       TEXT          NOT NULL,
    s_address    TEXT,
    s_nationkey  INTEGER       NOT NULL,
    s_phone      TEXT,
    s_acctbal    NUMERIC(15,2),
    s_comment    TEXT
);

CREATE TABLE tpch.customer (
    c_custkey     BIGINT        NOT NULL,
    c_name        TEXT          NOT NULL,
    c_address     TEXT,                    -- PII
    c_nationkey   INTEGER       NOT NULL,
    c_phone       TEXT,                    -- PII
    c_acctbal     NUMERIC(15,2),
    c_mktsegment  TEXT,
    c_comment     TEXT
);

CREATE TABLE tpch.part (
    p_partkey      BIGINT        NOT NULL,
    p_name         TEXT,
    p_mfgr         TEXT,
    p_brand        TEXT,
    p_type         TEXT,
    p_size         INTEGER,
    p_container    TEXT,
    p_retailprice  NUMERIC(15,2),
    p_comment      TEXT
);

CREATE TABLE tpch.partsupp (
    ps_partkey     BIGINT        NOT NULL,
    ps_suppkey     BIGINT        NOT NULL,
    ps_availqty    BIGINT,
    ps_supplycost  NUMERIC(15,2),
    ps_comment     TEXT
);

CREATE TABLE tpch.orders (
    o_orderkey       BIGINT        NOT NULL,
    o_custkey        BIGINT        NOT NULL,
    o_orderstatus    TEXT,
    o_totalprice     NUMERIC(15,2),
    o_orderdate      DATE          NOT NULL,
    o_orderpriority  TEXT,
    o_clerk          TEXT,
    o_shippriority   INTEGER,
    o_comment        TEXT
);

CREATE TABLE tpch.lineitem (
    l_orderkey       BIGINT        NOT NULL,
    l_partkey        BIGINT        NOT NULL,
    l_suppkey        BIGINT        NOT NULL,
    l_linenumber     BIGINT        NOT NULL,
    l_quantity       NUMERIC(15,2),
    l_extendedprice  NUMERIC(15,2),
    l_discount       NUMERIC(15,2),
    l_tax            NUMERIC(15,2),
    l_returnflag     TEXT,
    l_linestatus     TEXT,
    l_shipdate       DATE,
    l_commitdate     DATE,
    l_receiptdate    DATE,
    l_shipinstruct   TEXT,
    l_shipmode       TEXT,
    l_comment        TEXT
);
