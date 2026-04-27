from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from taxi_monitor.analytics import (
    airport_vs_manhattan,
    avg_fare_distance_by_zone,
    borough_flow_matrix,
    top_origin_destination_pairs,
    weekday_weekend_demand,
    zone_hour_heatmap,
)
from taxi_monitor.advanced_anomaly import detect_consensus_anomalies
from taxi_monitor.benchmarking import benchmark_anomaly_methods, benchmark_forecast_methods
from taxi_monitor.dashboard import build_dashboard
from taxi_monitor.database import init_schema, insert_clean_trips
from taxi_monitor.forecast import (
    backtest_zone_forecasts,
    ewm_forecast,
    forecast_next_horizon,
    moving_average_forecast,
    prepare_hourly_panel,
    seasonal_naive_forecast,
)


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


def _insert_toy_clean_trips(conn: duckdb.DuckDBPyConnection) -> None:
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


def _insert_toy_zone_lookup(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        INSERT INTO zone_lookup (location_id, borough, zone, service_zone)
        VALUES
            (1, 'Manhattan', 'Midtown Center', 'Yellow Zone'),
            (2, 'Queens', 'JFK Airport', 'Airports'),
            (3, 'Queens', 'LaGuardia Airport', 'Airports'),
            (4, 'Brooklyn', 'Downtown Brooklyn', 'Boro Zone')
        """
    )


def test_forecast_backtest_and_next_horizon():
    demand = _toy_demand()

    summary = backtest_zone_forecasts(demand, holdout_hours=24)
    assert not summary.empty

    future = forecast_next_horizon(demand, horizon=12)
    assert len(future) == 12 * demand["zone_id"].nunique()


def test_more_forecast_methods_run():
    demand = _toy_demand()
    panel = prepare_hourly_panel(demand)

    seasonal = seasonal_naive_forecast(panel, seasonal_lag=24)
    assert "yhat" in seasonal.columns

    moving = moving_average_forecast(panel, window=24)
    assert "yhat" in moving.columns

    ewm = ewm_forecast(panel, halflife=12)
    assert "yhat" in ewm.columns

    future_ma = forecast_next_horizon(
        demand,
        method="moving_average_24",
        horizon=6,
    )
    assert len(future_ma) == 6 * demand["zone_id"].nunique()

    future_ewm = forecast_next_horizon(
        demand,
        method="ewm_12",
        horizon=6,
    )
    assert len(future_ewm) == 6 * demand["zone_id"].nunique()


def test_forecast_invalid_method_raises():
    demand = _toy_demand()

    with pytest.raises(KeyError):
        forecast_next_horizon(demand, method="bad_method", horizon=6)


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


def test_dashboard_without_forecast_builds(tmp_path: Path):
    demand = _toy_demand()
    anomalies = detect_consensus_anomalies(demand, min_votes=1)

    fig = build_dashboard(
        demand,
        anomalies=anomalies,
        output_path=tmp_path / "dashboard_no_forecast.png",
    )

    assert (tmp_path / "dashboard_no_forecast.png").exists()
    fig.clf()


def test_benchmark_runs():
    demand = _toy_demand()

    out = benchmark_forecast_methods(demand)
    assert not out.empty


def test_benchmark_anomaly_methods_runs():
    demand = _toy_demand()

    out = benchmark_anomaly_methods(demand)
    assert not out.empty
    assert "name" in out.columns
    assert "seconds" in out.columns


def test_sql_analytics_runs():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _insert_toy_clean_trips(conn)

    out = weekday_weekend_demand(conn)
    assert not out.empty

    out = top_origin_destination_pairs(conn)
    assert not out.empty

    out = zone_hour_heatmap(conn)
    assert not out.empty

    out = avg_fare_distance_by_zone(conn)
    assert not out.empty


def test_more_sql_analytics_with_zone_lookup_runs():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    _insert_toy_clean_trips(conn)
    _insert_toy_zone_lookup(conn)

    airport = airport_vs_manhattan(conn)
    assert not airport.empty

    flows = borough_flow_matrix(conn)
    assert not flows.empty

    zone_summary = avg_fare_distance_by_zone(conn)
    assert not zone_summary.empty

def test_prepare_hourly_panel_missing_columns_raises():
    bad = pd.DataFrame({"pickup_hour": pd.date_range("2024-01-01", periods=3, freq="h")})

    with pytest.raises(ValueError):
        prepare_hourly_panel(bad)


def test_backtest_not_enough_history_raises():
    demand = pd.DataFrame(
        {
            "pickup_hour": pd.date_range("2024-01-01", periods=4, freq="h"),
            "zone_id": [1, 1, 1, 1],
            "trips": [1, 2, 3, 4],
        }
    )

    with pytest.raises(ValueError):
        backtest_zone_forecasts(demand, holdout_hours=24)