"""Step 1 of seeding TPC-H: download a pre-generated database and export it to Parquet.

Why download instead of `CALL dbgen(...)`: Windows Smart App Control blocks DuckDB's
tpch extension on the dev laptop. DuckDB publishes the same data pre-generated, and
reading it needs only core DuckDB. (See DESIGN.md D9.)

Usage:
    uv run python -m datasets.tpch.seed.download --sf 1     # ~250 MB  (development)
    uv run python -m datasets.tpch.seed.download --sf 10    # ~2.5 GB  (scale tests)

Output: data/tpch/sf<N>/<table>.parquet  (data/ is git-ignored)
"""

import argparse
import shutil
import urllib.request
from pathlib import Path

import duckdb

TABLES = ["region", "nation", "supplier", "customer", "part", "partsupp", "orders", "lineitem"]
DATA_ROOT = Path("data/tpch")


def download_db(sf: int) -> Path:
    """Download tpch-sf<N>.db once; skip if it's already on disk."""
    target = DATA_ROOT / f"tpch-sf{sf}.db"
    if target.exists():
        print(f"Already downloaded: {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://blobs.duckdb.org/data/tpch-sf{sf}.db"
    partial = target.with_suffix(".part")  # rename only when complete: no half files
    print(f"Downloading {url} ...")
    # The server rejects Python's default User-Agent ("Python-urllib") with 403.
    request = urllib.request.Request(url, headers={"User-Agent": "opsanalyst-seed/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response, open(partial, "wb") as f:
        shutil.copyfileobj(response, f)
    partial.rename(target)
    return target


def export_parquet(db_path: Path, sf: int) -> None:
    """Write one Parquet file per TPC-H table."""
    out_dir = DATA_ROOT / f"sf{sf}"
    out_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path), read_only=True) as con:
        for table in TABLES:
            out_file = out_dir / f"{table}.parquet"
            con.execute(f"COPY {table} TO '{out_file.as_posix()}' (FORMAT parquet)")
            rows = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"  {table:<9} {rows:>12,} rows -> {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sf", type=int, choices=[1, 10], default=1, help="scale factor")
    args = parser.parse_args()

    db_path = download_db(args.sf)
    export_parquet(db_path, args.sf)
    print("Done.")


if __name__ == "__main__":
    main()
