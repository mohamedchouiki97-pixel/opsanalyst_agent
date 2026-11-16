"""Step 2 of seeding TPC-H: load Parquet files into Postgres and build the company database.

DESTRUCTIVE: drops and recreates the "tpch" schema every run, so it's safe to re-run.

Usage:
    uv run python -m datasets.tpch.seed.load --sf 1

Steps (each one prints as it runs, so a failure shows exactly where it happened):
    1. recreate schema "tpch"
    2. 01_tables.sql            create empty tables
    3. bulk COPY                Parquet -> CSV -> Postgres (dates shifted +28 years)
    4. 02_keys_indexes.sql      keys + indexes
    5. 03_messiness.sql         realistic dirty data
    6. ../views.sql             business views
    7. 04_security.sql          roles, PII grants, row-level security
    8. ANALYZE                  refresh planner statistics (needed for EXPLAIN cost checks)
"""

import argparse
import time
from contextlib import closing
from pathlib import Path

import duckdb

from agent.db import connect

SEED_DIR = Path(__file__).parent
DATASET_DIR = SEED_DIR.parent
DATA_ROOT = Path("data/tpch")

# Load order matters only for readability here (FKs are added after loading).
TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]

# TPC-H dates run 1992-1998. Shifting +28 years gives 2020-2026, so questions like
# "last quarter" make sense today. 28 years keeps weekdays and leap years aligned.
DATE_SHIFT_YEARS = 28


def run_sql_file(conn, path: Path) -> None:
    print(f"  running {path.relative_to(DATASET_DIR)}")
    conn.execute_simple(path.read_text(encoding="utf-8"))


def copy_table(conn, duck, table: str, parquet_dir: Path, csv_dir: Path) -> None:
    """Parquet -> CSV (via DuckDB, shifting dates) -> Postgres COPY."""
    parquet = (parquet_dir / f"{table}.parquet").as_posix()
    csv_file = csv_dir / f"{table}.csv"

    # Build the SELECT list: shift DATE columns, keep everything else as-is.
    columns = duck.execute(f"DESCRIBE SELECT * FROM '{parquet}'").fetchall()
    select_list = ", ".join(
        f"CAST({name} + INTERVAL {DATE_SHIFT_YEARS} YEAR AS DATE) AS {name}"
        if col_type == "DATE"
        else name
        for name, col_type, *_ in columns
    )
    duck.execute(
        f"COPY (SELECT {select_list} FROM '{parquet}') "
        f"TO '{csv_file.as_posix()}' (FORMAT csv, HEADER false)"
    )

    start = time.perf_counter()
    with open(csv_file, "rb") as f:
        conn.run(f"COPY tpch.{table} FROM STDIN WITH (FORMAT csv)", stream=f)
    rows = conn.run(f"SELECT count(*) FROM tpch.{table}")[0][0]
    print(f"  {table:<9} {rows:>12,} rows  ({time.perf_counter() - start:.1f}s)")

    csv_file.unlink()  # CSVs are temporary; Parquet stays as the source of truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sf", type=int, choices=[1, 10], default=1, help="scale factor")
    args = parser.parse_args()

    parquet_dir = DATA_ROOT / f"sf{args.sf}"
    if not parquet_dir.exists():
        raise SystemExit(f"{parquet_dir} not found. Run: python -m datasets.tpch.seed.download")
    csv_dir = parquet_dir / "csv"
    csv_dir.mkdir(exist_ok=True)

    total_start = time.perf_counter()
    # timeout=None: building indexes on millions of rows takes longer than the default.
    with closing(connect(timeout=None)) as conn, duckdb.connect() as duck:
        print("1. Recreating schema tpch")
        conn.execute_simple("DROP SCHEMA IF EXISTS tpch CASCADE; CREATE SCHEMA tpch;")

        print("2. Creating tables")
        run_sql_file(conn, SEED_DIR / "01_tables.sql")

        print(f"3. Loading data (SF{args.sf}, dates +{DATE_SHIFT_YEARS} years)")
        for table in TABLES:
            copy_table(conn, duck, table, parquet_dir, csv_dir)

        print("4. Adding keys and indexes")
        run_sql_file(conn, SEED_DIR / "02_keys_indexes.sql")

        print("5. Adding realistic messiness")
        run_sql_file(conn, SEED_DIR / "03_messiness.sql")

        print("6. Creating business views")
        run_sql_file(conn, DATASET_DIR / "views.sql")

        print("7. Applying security (roles, PII grants, RLS)")
        run_sql_file(conn, SEED_DIR / "04_security.sql")

        print("8. Refreshing planner statistics")
        conn.execute_simple("ANALYZE;")

    print(f"Done in {time.perf_counter() - total_start:.0f}s.")


if __name__ == "__main__":
    main()
