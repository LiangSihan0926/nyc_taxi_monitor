"""Experiment 6 — Forecast backtesting.

Runs multiple forecasting methods on historical zone-hour demand data and
evaluates their performance. Outputs a summary table of results to
``reports/experiment_6_forecast.csv``.
"""
from __future__ import annotations

import argparse

import pandas as pd

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.database import connect
from taxi_monitor.forecast import backtest_zone_forecasts
from taxi_monitor.utils import DB_PATH, PROJECT_ROOT, ensure_dir, get_logger

logger = get_logger("experiment_6")


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

        results = backtest_zone_forecasts(demand)

        logger.info("Forecast backtest complete: %d rows", len(results))
        logger.info("Sample results:\n%s", results.head())

        out = out_dir / "experiment_6_forecast.csv"
        results.to_csv(out, index=False)

        logger.info("Saved forecast results to %s", out)

    finally:
        conn.close()


if __name__ == "__main__":
    main()