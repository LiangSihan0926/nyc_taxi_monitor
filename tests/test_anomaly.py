"""Tests for taxi_monitor.anomaly."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_monitor.anomaly import BaselineStats, detect_anomalies, fit_baseline, z_scores


@pytest.fixture
def two_week_demand():
    """Four weeks of synthetic hourly demand (despite the fixture name, kept
    for readability): zone 1 has a clean weekly rhythm, zone 2 is quiet, and
    we'll inject a surge in zone 1 at one specific hour.  Four weeks gives
    four observations per (zone, hour-of-week) bucket, which is enough for
    the population std to be stable."""
    hours = pd.date_range("2024-01-01", "2024-01-28 23:00", freq="1h")
    rng = np.random.default_rng(0)

    rows = []
    for ts in hours:
        # Zone 1: rhythm roughly 100 trips with moderate noise (σ ≈ 8)
        base = 100 + float(rng.normal(0, 8))
        rows.append({"pickup_hour": ts, "zone_id": 1, "trips": max(1.0, base)})
        # Zone 2: quiet
        rows.append(
            {"pickup_hour": ts, "zone_id": 2, "trips": float(abs(rng.normal(5, 2)))}
        )
    df = pd.DataFrame(rows)
    return df


def test_fit_baseline_shape(two_week_demand):
    baseline = fit_baseline(two_week_demand)
    # hour-of-week has 168 buckets × 2 zones, but only buckets that exist in
    # the data are present.
    assert set(baseline.table.columns) >= {"zone_id", "hour_of_week", "mean", "std", "n"}
    assert len(baseline.table) <= 168 * 2


def test_baseline_lookup(two_week_demand):
    baseline = fit_baseline(two_week_demand)
    m, s, n = baseline.lookup(1, 0)
    assert m > 50  # zone 1 averages ~100
    assert s >= 0
    assert n >= 1
    assert baseline.lookup(999, 0) is None


def test_z_scores_flag_synthetic_surge(two_week_demand):
    # Inject a 5x surge at one specific (zone, hour).
    target = pd.Timestamp("2024-01-15 08:00")
    spike_row = pd.DataFrame(
        [{"pickup_hour": target, "zone_id": 1, "trips": 900}]
    )
    current = spike_row
    baseline = fit_baseline(two_week_demand)

    scored = z_scores(current, baseline)
    z = scored.iloc[0]["z"]
    assert z is not None and z > 5

    flagged = detect_anomalies(current, baseline, threshold=3.0)
    assert not flagged.empty
    assert flagged.iloc[0]["zone_id"] == 1


def test_z_scores_nan_when_std_too_small(two_week_demand):
    # Build a degenerate baseline where std is 0.
    const_df = two_week_demand.copy()
    const_df.loc[const_df["zone_id"] == 2, "trips"] = 5
    baseline = fit_baseline(const_df)
    scored = z_scores(
        const_df[const_df["zone_id"] == 2], baseline, min_std=1.0
    )
    assert scored["z"].isna().all()


def test_detect_anomalies_handles_empty_input(two_week_demand):
    baseline = fit_baseline(two_week_demand)
    empty = pd.DataFrame(
        {"pickup_hour": pd.to_datetime([]), "zone_id": [], "trips": []}
    )
    out = detect_anomalies(empty, baseline)
    assert out.empty
