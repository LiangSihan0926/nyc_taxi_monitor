"""End-to-end batch pipeline: ingest → clean → load into DuckDB.

Usage
-----
    python scripts/run_pipeline.py                         # default months
    python scripts/run_pipeline.py --months 2024-01
    python scripts/run_pipeline.py --db data/taxi.duckdb
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple

from taxi_monitor.clean import clean_trips
from taxi_monitor.database import (
    connect,
    count_rows,
    drop_all,
    init_schema,
    insert_clean_trips,
    insert_zone_lookup,
)
from taxi_monitor.ingest import load_trips, load_zone_lookup
from taxi_monitor.utils import DB_PATH, RAW_DIR, get_logger

logger = get_logger("run_pipeline")


def parse_month(s: str) -> Tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def month_file(raw_dir: Path, year: int, month: int) -> Path:
    return raw_dir / f"yellow_tripdata_{year:04d}-{month:02d}.parquet"


def run(
    months: Iterable[Tuple[int, int]],
    raw_dir: Path,
    db_path: Path,
    *,
    reset: bool = True,
) -> dict:
    conn = connect(db_path)
    try:
        if reset:
            drop_all(conn)
        init_schema(conn)

        zone_csv = raw_dir / "taxi_zone_lookup.csv"
        if zone_csv.exists():
            insert_zone_lookup(conn, load_zone_lookup(zone_csv))
            logger.info("loaded zone_lookup (%d rows)", count_rows(conn, "zone_lookup"))
        else:
            logger.warning("zone lookup not found at %s (skipping)", zone_csv)

        total_in = total_out = 0
        reports: List[dict] = []
        for year, month in months:
            path = month_file(raw_dir, year, month)
            if not path.exists():
                raise FileNotFoundError(
                    f"{path} missing — run scripts/download_data.py first"
                )
            raw = load_trips(path)
            clean_df, report = clean_trips(raw)
            insert_clean_trips(conn, clean_df)
            total_in += report.input_rows
            total_out += report.output_rows
            reports.append({"month": f"{year}-{month:02d}", **report.as_dict()})

        summary = {
            "db_path": str(db_path),
            "months": [f"{y}-{m:02d}" for y, m in months],
            "input_rows": total_in,
            "output_rows": total_out,
            "clean_trips_in_db": count_rows(conn, "clean_trips"),
            "per_month": reports,
        }
        return summary
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        nargs="+",
        metavar="YYYY-MM",
        default=["2024-01"],
        help="Months to ingest (default: 2024-01)",
    )
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument(
        "--append", action="store_true", help="Do not drop existing tables"
    )
    args = parser.parse_args()

    months = [parse_month(m) for m in args.months]
    summary = run(
        months,
        Path(args.raw_dir),
        Path(args.db),
        reset=not args.append,
    )

    logger.info("--- pipeline summary ---")
    for k in ("db_path", "months", "input_rows", "output_rows", "clean_trips_in_db"):
        logger.info("  %s: %s", k, summary[k])


if __name__ == "__main__":
    main()
