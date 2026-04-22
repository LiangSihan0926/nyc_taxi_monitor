"""Module 1b: Data cleaning.

Turns a raw Yellow Taxi DataFrame into a clean, typed DataFrame suitable for
SQL aggregation.  Every filter is idempotent and logged so the pipeline is
fully reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd

from .utils import get_logger

__all__ = ["CleaningReport", "clean_trips"]

logger = get_logger(__name__)


@dataclass
class CleaningReport:
    """Summary of what `clean_trips` did — useful for tests and for the
    reproducibility story in the final writeup."""

    input_rows: int
    output_rows: int
    dropped: Dict[str, int]

    @property
    def total_dropped(self) -> int:
        return self.input_rows - self.output_rows

    def as_dict(self) -> Dict[str, int]:
        return {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "total_dropped": self.total_dropped,
            **{f"dropped_{k}": v for k, v in self.dropped.items()},
        }


# Valid NYC TLC LocationIDs are 1..263.  265 also appears (Outside of NYC /
# Unknown) but is not meaningful for demand analysis, so we drop it.
VALID_ZONE_MIN = 1
VALID_ZONE_MAX = 263

# Reasonable trip bounds.  These are intentionally loose — the goal is to drop
# obvious garbage, not to over-filter.
MIN_TRIP_SECONDS = 30
MAX_TRIP_SECONDS = 6 * 60 * 60  # 6 hours
MIN_TRIP_DISTANCE = 0.0
MAX_TRIP_DISTANCE = 100.0  # miles

# TLC parquet files occasionally contain rows with nonsense pickup
# timestamps (e.g. 2002-12-31, 2009-01-01) that pass all other filters.
# Year < 2010 is a safe floor — TLC electronic trip records only started
# in 2009 and Yellow Taxi LocationID encoding only stabilised in 2011.
MIN_PICKUP_YEAR = 2010


def clean_trips(
    df: pd.DataFrame,
    *,
    pickup_col: str = "tpep_pickup_datetime",
    dropoff_col: str = "tpep_dropoff_datetime",
    pu_zone_col: str = "PULocationID",
    do_zone_col: str = "DOLocationID",
    distance_col: str = "trip_distance",
    fare_col: str = "fare_amount",
) -> tuple[pd.DataFrame, CleaningReport]:
    """Return `(clean_df, report)`.

    Cleaning steps (order matters; later steps assume prior ones succeeded):
      1. Drop rows with NaNs in required columns.
      2. Parse datetime columns and drop rows where parsing failed.
      3. Drop rows with non-positive trip duration or duration > 6h.
      4. Drop rows with pickup year < `MIN_PICKUP_YEAR` (nonsense dates).
      5. Drop rows with invalid zone IDs.
      6. Drop rows with negative fares or absurd distances.
      7. De-duplicate exact duplicate rows.
      8. Derive `trip_duration_sec`, `pickup_hour`, `pickup_date`.
    """
    original = len(df)
    dropped: Dict[str, int] = {}
    df = df.copy()

    required = [pickup_col, dropoff_col, pu_zone_col, do_zone_col]

    # 1. Missing values
    before = len(df)
    df = df.dropna(subset=required)
    dropped["missing_required"] = before - len(df)

    # 2. Datetime parsing
    df[pickup_col] = pd.to_datetime(df[pickup_col], errors="coerce")
    df[dropoff_col] = pd.to_datetime(df[dropoff_col], errors="coerce")
    before = len(df)
    df = df.dropna(subset=[pickup_col, dropoff_col])
    dropped["bad_datetime"] = before - len(df)

    # 3. Trip duration
    duration = (df[dropoff_col] - df[pickup_col]).dt.total_seconds()
    before = len(df)
    mask = (duration >= MIN_TRIP_SECONDS) & (duration <= MAX_TRIP_SECONDS)
    df = df.loc[mask].copy()
    duration = duration.loc[mask]
    dropped["bad_duration"] = before - len(df)

    # 4. Pickup date sanity (catch nonsense timestamps like 2002, 2009)
    before = len(df)
    mask = df[pickup_col].dt.year >= MIN_PICKUP_YEAR
    df = df.loc[mask].copy()
    duration = duration.loc[mask]
    dropped["bad_date"] = before - len(df)

    # 5. Zone IDs must be integers in [1, 263]
    before = len(df)
    for col in (pu_zone_col, do_zone_col):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    mask = (
        df[pu_zone_col].between(VALID_ZONE_MIN, VALID_ZONE_MAX)
        & df[do_zone_col].between(VALID_ZONE_MIN, VALID_ZONE_MAX)
    )
    df = df.loc[mask].copy()
    duration = duration.loc[mask]
    dropped["bad_zone"] = before - len(df)

    # 6. Fare / distance sanity
    before = len(df)
    good = pd.Series(True, index=df.index)
    if distance_col in df.columns:
        dist = pd.to_numeric(df[distance_col], errors="coerce")
        good &= dist.between(MIN_TRIP_DISTANCE, MAX_TRIP_DISTANCE, inclusive="both")
        df[distance_col] = dist
    if fare_col in df.columns:
        fare = pd.to_numeric(df[fare_col], errors="coerce")
        good &= fare >= 0
        df[fare_col] = fare
    df = df.loc[good].copy()
    duration = duration.loc[good]
    dropped["bad_fare_distance"] = before - len(df)

    # 7. Exact duplicates
    before = len(df)
    df = df.drop_duplicates()
    duration = duration.loc[df.index]
    dropped["duplicates"] = before - len(df)

    # 8. Derived columns used by aggregation / hotspot / streaming.
    df["trip_duration_sec"] = duration.astype(np.int64)
    df["pickup_hour"] = df[pickup_col].dt.floor("h")
    df["pickup_date"] = df[pickup_col].dt.date
    df[pu_zone_col] = df[pu_zone_col].astype(np.int64)
    df[do_zone_col] = df[do_zone_col].astype(np.int64)
    df = df.reset_index(drop=True)

    report = CleaningReport(
        input_rows=original, output_rows=len(df), dropped=dropped
    )
    logger.info(
        "clean_trips: %s -> %s rows (dropped %s)",
        f"{report.input_rows:,}",
        f"{report.output_rows:,}",
        f"{report.total_dropped:,}",
    )
    return df, report
