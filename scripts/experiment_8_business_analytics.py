"""Experiment 8 — Business analytics queries.

Runs a set of SQL-based business analytics queries on the cleaned taxi dataset,
including:

  * weekday vs weekend demand patterns
  * top origin-destination pairs
  * airport vs Manhattan demand comparison

Outputs results to CSV files under ``reports/``.
"""
from __future__ import annotations

import argparse

from taxi_monitor.analytics import (
    airport_vs_manhattan,
    top_origin_destination_pairs,
    weekday_weekend_demand,
)
from taxi_monitor.database import connect
from taxi_monitor.utils import DB_PATH, PROJECT_ROOT, ensure_dir, get_logger

logger = get_logger("experiment_8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "reports"))
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    conn = connect(args.db)

    try:
        logger.info("Running weekday vs weekend demand analysis...")
        df_week = weekday_weekend_demand(conn)
        logger.info("Result shape: %s", df_week.shape)

        logger.info("Sample:\n%s", df_week.head())

        df_week.to_csv(out_dir / "weekday_weekend_demand.csv", index=False)

        logger.info("Running top origin-destination pairs analysis...")
        df_od = top_origin_destination_pairs(conn)
        logger.info("Top OD pairs: %d rows", len(df_od))

        logger.info("Sample:\n%s", df_od.head())

        df_od.to_csv(out_dir / "top_od_pairs.csv", index=False)

        logger.info("Running airport vs Manhattan comparison...")
        df_air = airport_vs_manhattan(conn)
        logger.info("Airport vs Manhattan rows: %d", len(df_air))

        logger.info("Sample:\n%s", df_air.head())

        df_air.to_csv(out_dir / "airport_vs_manhattan.csv", index=False)

        logger.info("Saved analytics outputs to %s", out_dir)

    finally:
        conn.close()


if __name__ == "__main__":
    main()