"""Experiment 1 — Batch hotspot detection.

For each of several time windows, print the top-k busiest zones and write the
full per-hour top-k table to ``reports/experiment_1_hotspots.csv``.
"""
from __future__ import annotations

import argparse

from taxi_monitor.aggregate import busiest_zones, zone_hour_demand
from taxi_monitor.database import connect
from taxi_monitor.hotspot import top_k_per_window
from taxi_monitor.utils import DB_PATH, PROJECT_ROOT, ensure_dir, get_logger

logger = get_logger("experiment_1")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--k", type=int, default=10)
    p.add_argument(
        "--out-dir", default=str(PROJECT_ROOT / "reports"), help="output dir"
    )
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    conn = connect(args.db)
    try:
        # (a) city-wide top-k across the whole DB
        overall = busiest_zones(conn, k=args.k)
        logger.info("Overall top-%d busiest pickup zones:\n%s", args.k, overall)
        overall.to_csv(out_dir / "experiment_1_overall.csv", index=False)

        # (b) per-hour top-k
        demand = zone_hour_demand(conn)
        per_hour = top_k_per_window(demand, k=args.k)
        per_hour.to_csv(out_dir / "experiment_1_per_hour.csv", index=False)
        logger.info(
            "Per-hour top-%d table has %d rows (across %d hours)",
            args.k,
            len(per_hour),
            per_hour["pickup_hour"].nunique(),
        )

        # Show the very first hour as a sanity check
        if not per_hour.empty:
            first_hour = per_hour["pickup_hour"].min()
            sample = per_hour[per_hour["pickup_hour"] == first_hour]
            logger.info("Example window (%s):\n%s", first_hour, sample)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
