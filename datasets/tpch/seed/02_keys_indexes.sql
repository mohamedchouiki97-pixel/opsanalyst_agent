-- 02: Primary keys, foreign keys and indexes (run AFTER the bulk load).

-- Primary keys
ALTER TABLE tpch.region   ADD PRIMARY KEY (r_regionkey);
ALTER TABLE tpch.nation   ADD PRIMARY KEY (n_nationkey);
ALTER TABLE tpch.supplier ADD PRIMARY KEY (s_suppkey);
ALTER TABLE tpch.customer ADD PRIMARY KEY (c_custkey);
ALTER TABLE tpch.part     ADD PRIMARY KEY (p_partkey);
ALTER TABLE tpch.partsupp ADD PRIMARY KEY (ps_partkey, ps_suppkey);
ALTER TABLE tpch.orders   ADD PRIMARY KEY (o_orderkey);
ALTER TABLE tpch.lineitem ADD PRIMARY KEY (l_orderkey, l_linenumber);

-- Foreign keys (they also document the joins for profile_dataset.py and the agent)
ALTER TABLE tpch.nation   ADD FOREIGN KEY (n_regionkey) REFERENCES tpch.region (r_regionkey);
ALTER TABLE tpch.supplier ADD FOREIGN KEY (s_nationkey) REFERENCES tpch.nation (n_nationkey);
ALTER TABLE tpch.customer ADD FOREIGN KEY (c_nationkey) REFERENCES tpch.nation (n_nationkey);
ALTER TABLE tpch.partsupp ADD FOREIGN KEY (ps_partkey)  REFERENCES tpch.part (p_partkey);
ALTER TABLE tpch.partsupp ADD FOREIGN KEY (ps_suppkey)  REFERENCES tpch.supplier (s_suppkey);
ALTER TABLE tpch.orders   ADD FOREIGN KEY (o_custkey)   REFERENCES tpch.customer (c_custkey);
ALTER TABLE tpch.lineitem ADD FOREIGN KEY (l_orderkey)  REFERENCES tpch.orders (o_orderkey);
ALTER TABLE tpch.lineitem ADD FOREIGN KEY (l_partkey, l_suppkey)
                                          REFERENCES tpch.partsupp (ps_partkey, ps_suppkey);

-- Indexes on join keys (Postgres does NOT index foreign key columns automatically)
CREATE INDEX ON tpch.nation   (n_regionkey);
CREATE INDEX ON tpch.supplier (s_nationkey);
CREATE INDEX ON tpch.customer (c_nationkey);
CREATE INDEX ON tpch.partsupp (ps_suppkey);
CREATE INDEX ON tpch.orders   (o_custkey);
CREATE INDEX ON tpch.lineitem (l_partkey, l_suppkey);
CREATE INDEX ON tpch.lineitem (l_suppkey);

-- Indexes on dates (most business questions filter by a period)
CREATE INDEX ON tpch.orders   (o_orderdate);
CREATE INDEX ON tpch.lineitem (l_shipdate);
CREATE INDEX ON tpch.lineitem (l_receiptdate);
