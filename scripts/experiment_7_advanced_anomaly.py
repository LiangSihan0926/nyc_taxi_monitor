"""Experiment 7 — Advanced anomaly detection.

Applies multiple anomaly detection methods (robust z-score and EWMA residuals)
and flags anomalies based on consensus voting across detectors.

Outputs flagged anomalies to
``reports/experiment_7_advanced_anomaly.csv``.
"""
from __future__ import annotations

import argparse

import pandas as pd

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.advanced_anomaly import detect_consensus_anomalies
from taxi_monitor.database import connect
from taxi_monitor.utils import DB_PATH, PROJECT_ROOT, ensure_dir, get_logger

logger = get_logger("experiment_7")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "reports"))
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    conn = connect(args.db)

    try:
        demand = zone_hour_demand(conn)

        if not isinstance(demand, pd.DataFrame):
            demand = pd.DataFrame(demand)

        logger.info("Loaded demand data with %d rows", len(demand))

        logger.info("Running consensus anomaly detection...")
        results = detect_consensus_anomalies(demand)

        logger.info("Detected %d anomalies", len(results))

        if not results.empty:
            logger.info("Top anomalies:\n%s", results.head(10))

        out = out_dir / "experiment_7_advanced_anomaly.csv"
        results.to_csv(out, index=False)

        logger.info("Saved advanced anomaly results to %s", out)

    finally:
        conn.close()


if __name__ == "__main__":
    main()