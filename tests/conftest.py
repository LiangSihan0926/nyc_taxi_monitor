"""Shared pytest fixtures.

All fixtures are in-memory / on tmp_path so tests never touch the network or
the real ``data/`` directory.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from taxi_monitor.utils import set_seed


@pytest.fixture(autouse=True)
def _seed_everything():
    """Every test starts from the same random seed."""
    set_seed(42)


@pytest.fixture
def raw_trips_df() -> pd.DataFrame:
    """Synthetic 'raw' Yellow Taxi DataFrame — includes some dirty rows so
    `clean_trips` has something to filter."""
    rng = np.random.default_rng(42)
    n = 200

    pickups = pd.date_range("2024-01-01 00:00:00", periods=n, freq="1min")
    # ~5 minute trip durations, but we'll corrupt a few below
    durations = pd.to_timedelta(rng.integers(60, 15 * 60, size=n), unit="s")
    dropoffs = pickups + durations

    df = pd.DataFrame(
        {
            "tpep_pickup_datetime": pickups,
            "tpep_dropoff_datetime": dropoffs,
            "passenger_count": rng.integers(1, 5, size=n),
            "trip_distance": rng.uniform(0.5, 10, size=n),
            "PULocationID": rng.integers(1, 264, size=n),
            "DOLocationID": rng.integers(1, 264, size=n),
            "fare_amount": rng.uniform(5, 40, size=n),
            "total_amount": rng.uniform(7, 50, size=n),
        }
    )

    # Inject dirt:
    df.loc[0, "PULocationID"] = 999  # invalid zone
    df.loc[1, "tpep_dropoff_datetime"] = df.loc[1, "tpep_pickup_datetime"]  # 0-sec trip
    df.loc[2, "trip_distance"] = -1  # negative distance
    df.loc[3, "PULocationID"] = np.nan
    df.loc[4, "fare_amount"] = -10
    # an exact duplicate
    df.loc[5] = df.loc[6]

    return df


@pytest.fixture
def raw_trips_parquet(tmp_path: Path, raw_trips_df: pd.DataFrame) -> Path:
    """Write `raw_trips_df` to a temporary parquet file."""
    path = tmp_path / "yellow_tripdata_2024-01.parquet"
    raw_trips_df.to_parquet(path)
    return path


@pytest.fixture
def zone_lookup_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "LocationID": [1, 2, 3, 100, 263],
            "Borough": ["Manhattan", "Manhattan", "Queens", "Bronx", "Queens"],
            "Zone": ["A", "B", "C", "D", "E"],
            "service_zone": ["Yellow", "Yellow", "Boro", "Boro", "Boro"],
        }
    )


@pytest.fixture
def zone_lookup_csv(tmp_path: Path, zone_lookup_df: pd.DataFrame) -> Path:
    path = tmp_path / "taxi_zone_lookup.csv"
    zone_lookup_df.to_csv(path, index=False)
    return path


@pytest.fixture
def demand_df() -> pd.DataFrame:
    """A tiny (hour × zone) demand table.  Zone 1 is the hotspot, zone 3 has
    a big spike at hour 4."""
    rows = []
    for hour in range(5):
        ts = pd.Timestamp("2024-01-01 00:00:00") + pd.Timedelta(hours=hour)
        rows.append({"pickup_hour": ts, "zone_id": 1, "trips": 100 + hour})
        rows.append({"pickup_hour": ts, "zone_id": 2, "trips": 50 + hour})
        # zone 3 has normal demand then a surge
        rows.append(
            {
                "pickup_hour": ts,
                "zone_id": 3,
                "trips": 10 if hour < 4 else 500,
            }
        )
    return pd.DataFrame(rows)
