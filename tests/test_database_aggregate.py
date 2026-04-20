"""Tests for taxi_monitor.database + taxi_monitor.aggregate (shared fixtures)."""
from __future__ import annotations

import pandas as pd
import pytest

from taxi_monitor import aggregate, database
from taxi_monitor.clean import clean_trips


@pytest.fixture
def loaded_conn(raw_trips_df, zone_lookup_df):
    clean_df, _ = clean_trips(raw_trips_df)
    conn = database.connect(":memory:")
    database.init_schema(conn)
    database.insert_zone_lookup(conn, zone_lookup_df)
    database.insert_clean_trips(conn, clean_df)
    yield conn
    conn.close()


def test_connect_memory():
    conn = database.connect(":memory:")
    database.init_schema(conn)
    assert database.table_exists(conn, "clean_trips")
    assert database.table_exists(conn, "zone_lookup")
    conn.close()


def test_connect_path(tmp_path):
    p = tmp_path / "a" / "b" / "test.duckdb"
    conn = database.connect(p)
    database.init_schema(conn)
    conn.close()
    assert p.exists()


def test_insert_empty_is_noop():
    conn = database.connect(":memory:")
    database.init_schema(conn)
    inserted = database.insert_clean_trips(conn, pd.DataFrame())
    assert inserted == 0
    assert database.count_rows(conn, "clean_trips") == 0
    conn.close()


def test_insert_replace_clears_first(raw_trips_df):
    clean_df, _ = clean_trips(raw_trips_df)
    conn = database.connect(":memory:")
    database.init_schema(conn)
    database.insert_clean_trips(conn, clean_df)
    before = database.count_rows(conn, "clean_trips")
    database.insert_clean_trips(conn, clean_df, replace=True)
    after = database.count_rows(conn, "clean_trips")
    assert before == after  # same rows, inserted twice w/ reset each time
    conn.close()


def test_drop_all(loaded_conn):
    assert database.count_rows(loaded_conn, "clean_trips") > 0
    database.drop_all(loaded_conn)
    assert not database.table_exists(loaded_conn, "clean_trips")
    assert not database.table_exists(loaded_conn, "zone_lookup")


# --- aggregate --------------------------------------------------------------


def test_zone_hour_demand(loaded_conn):
    df = aggregate.zone_hour_demand(loaded_conn)
    assert {"pickup_hour", "zone_id", "trips"} <= set(df.columns)
    assert (df["trips"] > 0).all()


def test_zone_daily_demand(loaded_conn):
    df = aggregate.zone_daily_demand(loaded_conn)
    assert {"pickup_date", "zone_id", "trips"} <= set(df.columns)


def test_busiest_zones_with_lookup(loaded_conn):
    df = aggregate.busiest_zones(loaded_conn, k=3)
    assert {"zone_id", "zone_name", "borough", "trips"} <= set(df.columns)
    assert len(df) <= 3
    assert df["trips"].is_monotonic_decreasing


def test_busiest_zones_time_filter(loaded_conn):
    df = aggregate.busiest_zones(
        loaded_conn, k=10, since="2024-01-01 00:00:00", until="2024-01-01 00:30:00"
    )
    # Window is 30 minutes of the fixture — should return non-empty, and
    # every row corresponds to a real zone_id (1..263).
    assert not df.empty
    assert (df["zone_id"].between(1, 263)).all()


def test_busiest_zones_without_lookup(raw_trips_df):
    clean_df, _ = clean_trips(raw_trips_df)
    conn = database.connect(":memory:")
    database.init_schema(conn)
    database.drop_all(conn, ["zone_lookup"])  # explicitly drop the lookup
    database.insert_clean_trips(conn, clean_df)
    df = aggregate.busiest_zones(conn, k=3)
    assert set(df.columns) == {"zone_id", "trips"}
    conn.close()


def test_demand_distribution(loaded_conn):
    df = aggregate.demand_distribution(loaded_conn)
    assert {"zone_id", "mean_trips", "std_trips", "min_trips", "max_trips"} <= set(
        df.columns
    )


def test_hourly_totals(loaded_conn):
    df = aggregate.hourly_totals(loaded_conn)
    assert list(df.columns) == ["pickup_hour", "trips"]
    assert df["trips"].sum() > 0
