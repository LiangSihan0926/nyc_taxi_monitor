"""Experiment 2 — Anomaly / demand-surge detection.

Uses November–December 2023 (already loaded in DuckDB) as the baseline and
January 2024 as the "current" period, then flags (zone, hour) cells whose
z-score exceeds the threshold.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.anomaly import detect_anomalies, fit_baseline
from taxi_monitor.database import connect
from taxi_monitor.utils import DB_PATH, PROJECT_ROOT, ensure_dir, get_logger

logger = get_logger("experiment_2")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument(
        "--baseline-end", default="2024-01-01", help="Baseline includes hours < this"
    )
    p.add_argument("--threshold", type=float, default=3.0)
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "reports"))
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    conn = connect(args.db)
    try:
        demand = zone_hour_demand(conn)
        baseline_df = demand[demand["pickup_hour"] < args.baseline_end]
        current_df = demand[demand["pickup_hour"] >= args.baseline_end]

        if baseline_df.empty or current_df.empty:
            logger.warning(
                "Need data both before and after %s; "
                "baseline=%d rows, current=%d rows",
                args.baseline_end,
                len(baseline_df),
                len(current_df),
            )
            return

        baseline = fit_baseline(baseline_df)
        baseline.table.to_csv(out_dir / "experiment_2_baseline.csv", index=False)

        anomalies = detect_anomalies(current_df, baseline, threshold=args.threshold)
        anomalies.to_csv(out_dir / "experiment_2_anomalies.csv", index=False)
        logger.info("flagged %d anomalies (|z| >= %.1f)", len(anomalies), args.threshold)

        if not anomalies.empty:
            logger.info("Top 10 surges:\n%s", anomalies.head(10))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
