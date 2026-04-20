"""Tests for taxi_monitor.clean."""
from __future__ import annotations

import pandas as pd
import pytest

from taxi_monitor.clean import CleaningReport, clean_trips


def test_clean_drops_dirty_rows(raw_trips_df: pd.DataFrame):
    clean, report = clean_trips(raw_trips_df)

    assert isinstance(report, CleaningReport)
    assert report.input_rows == len(raw_trips_df)
    assert report.output_rows <= report.input_rows
    assert report.total_dropped >= 3  # at least our injected bad rows
    assert report.dropped["bad_zone"] >= 1
    assert report.dropped["bad_duration"] >= 1
    assert report.dropped["bad_fare_distance"] >= 1
    assert report.dropped["missing_required"] >= 1


def test_clean_adds_derived_columns(raw_trips_df: pd.DataFrame):
    clean, _ = clean_trips(raw_trips_df)
    for col in ("trip_duration_sec", "pickup_hour", "pickup_date"):
        assert col in clean.columns
    # duration is a positive integer
    assert (clean["trip_duration_sec"] > 0).all()
    # pickup_hour is at hour resolution
    assert (clean["pickup_hour"].dt.minute == 0).all()


def test_clean_is_idempotent(raw_trips_df: pd.DataFrame):
    once, _ = clean_trips(raw_trips_df)
    # clean_trips expects raw-style datetime columns; after a first pass the
    # data is already clean so a second pass must not drop any more rows.
    twice, report2 = clean_trips(once)
    assert len(twice) == len(once)
    assert report2.total_dropped == 0


def test_clean_empty_frame():
    df = pd.DataFrame(
        columns=[
            "tpep_pickup_datetime",
            "tpep_dropoff_datetime",
            "PULocationID",
            "DOLocationID",
            "trip_distance",
            "fare_amount",
        ]
    )
    clean, report = clean_trips(df)
    assert clean.empty
    assert report.output_rows == 0


def test_report_as_dict(raw_trips_df):
    _, report = clean_trips(raw_trips_df)
    d = report.as_dict()
    assert d["input_rows"] == report.input_rows
    assert d["output_rows"] == report.output_rows
    assert "dropped_bad_zone" in d
