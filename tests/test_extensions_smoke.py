from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from taxi_monitor.analytics import (
    avg_fare_distance_by_zone,
    top_origin_destination_pairs,
    weekday_weekend_demand,
    zone_hour_heatmap,
)
from taxi_monitor.advanced_anomaly import detect_consensus_anomalies
from taxi_monitor.benchmarking import benchmark_forecast_methods
from taxi_monitor.dashboard import build_dashboard
from taxi_monitor.database import init_schema, insert_clean_trips
from taxi_monitor.forecast import backtest_zone_forecasts, forecast_next_horizon


def _toy_demand() -> pd.DataFrame:
    rows = []
    hours = pd.date_range("2024-01-01", periods=24 * 14, freq="h")

    for ts in hours:
        rows.append(
            {
                "pickup_hour": ts,
                "zone_id": 1,
                "trips": 10 + (ts.hour in {8, 9, 17, 18}) * 5,
            }
        )
        rows.append(
            {
                "pickup_hour": ts,
                "zone_id": 2,
                "trips": 6 + (ts.dayofweek >= 5) * 3,
            }
        )

    return pd.DataFrame(rows)


def test_forecast_backtest_and_next_horizon():
    demand = _toy_demand()

    summary = backtest_zone_forecasts(demand, holdout_hours=24)
    assert not summary.empty

    future = forecast_next_horizon(demand, horizon=12)
    assert len(future) == 12 * demand["zone_id"].nunique()


def test_consensus_anomalies_runs():
    demand = _toy_demand()

    demand.loc[
        (demand["zone_id"] == 1)
        & (demand["pickup_hour"] == demand["pickup_hour"].max()),
        "trips",
    ] = 100

    flagged = detect_consensus_anomalies(demand)
    assert isinstance(flagged, pd.DataFrame)


def test_dashboard_builds(tmp_path: Path):
    demand = _toy_demand()
    future = forecast_next_horizon(demand, horizon=6)

    fig = build_dashboard(
        demand,
        forecast=future,
        output_path=tmp_path / "dashboard.png",
    )

    assert (tmp_path / "dashboard.png").exists()
    fig.clf()


def test_benchmark_runs():
    demand = _toy_demand()

    out = benchmark_forecast_methods(demand)
    assert not out.empty


def test_sql_analytics_runs():
    conn = duckdb.connect(":memory:")
    init_schema(conn)

    raw = pd.DataFrame(
        {
            "tpep_pickup_datetime": pd.date_range(
                "2024-01-01",
                periods=8,
                freq="h",
            ),
            "tpep_dropoff_datetime": pd.date_range(
                "2024-01-01 00:10",
                periods=8,
                freq="h",
            ),
            "PULocationID": [1, 1, 2, 2, 3, 3, 4, 4],
            "DOLocationID": [2, 3, 3, 4, 4, 1, 1, 2],
            "passenger_count": [1] * 8,
            "trip_distance": [1.2] * 8,
            "fare_amount": [10.0] * 8,
            "total_amount": [13.0] * 8,
            "trip_duration_sec": [600] * 8,
            "pickup_hour": pd.date_range(
                "2024-01-01",
                periods=8,
                freq="h",
            ),
            "pickup_date": pd.date_range(
                "2024-01-01",
                periods=8,
                freq="h",
            ).date,
        }
    )

    insert_clean_trips(conn, raw)

    out = weekday_weekend_demand(conn)
    assert not out.empty

    out = top_origin_destination_pairs(conn)
    assert not out.empty

    out = zone_hour_heatmap(conn)
    assert not out.empty

    out = avg_fare_distance_by_zone(conn)
    assert not out.empty