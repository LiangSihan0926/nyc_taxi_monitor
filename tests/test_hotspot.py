"""Tests for taxi_monitor.hotspot."""
from __future__ import annotations

import random

import pandas as pd
import pytest

from taxi_monitor.hotspot import (
    HotspotResult,
    top_k_from_counts,
    top_k_heap,
    top_k_per_window,
)


def test_top_k_basic():
    counts = {1: 10, 2: 30, 3: 20, 4: 5}
    top = top_k_from_counts(counts, 2)
    assert [r.zone_id for r in top] == [2, 3]
    assert [r.rank for r in top] == [1, 2]


def test_top_k_k_zero_returns_empty():
    assert top_k_heap([(1, 5)], 0) == []


def test_top_k_k_larger_than_input():
    out = top_k_from_counts({1: 3, 2: 1}, 10)
    assert len(out) == 2


def test_top_k_ties_are_deterministic():
    # all zones tied — output must be deterministic (sorted by zone_id asc).
    counts = {z: 7 for z in [5, 1, 3, 2, 4]}
    a = top_k_from_counts(counts, 3)
    b = top_k_from_counts(counts, 3)
    assert [r.zone_id for r in a] == [r.zone_id for r in b]
    # And specifically the smaller zone_ids come first.
    assert [r.zone_id for r in a] == [1, 2, 3]


def test_top_k_ignores_none_counts():
    items = [(1, 10), (2, None), (3, 5)]
    out = top_k_heap(items, 5)
    assert [r.zone_id for r in out] == [1, 3]


def test_top_k_matches_brute_force_on_random_data():
    rng = random.Random(0)
    counts = {i: rng.randint(0, 10_000) for i in range(1, 264)}
    expected = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    heap_out = [(r.zone_id, r.count) for r in top_k_from_counts(counts, 20)]
    assert heap_out == expected


def test_top_k_per_window(demand_df: pd.DataFrame):
    out = top_k_per_window(demand_df, k=2)
    assert set(out.columns) == {"pickup_hour", "rank", "zone_id", "trips"}
    # Every window has exactly 2 rows (there are 3 zones, k=2)
    per_hour = out.groupby("pickup_hour").size()
    assert (per_hour == 2).all()


def test_top_k_per_window_validates_columns():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError):
        top_k_per_window(df)


def test_hotspot_result_is_frozen():
    r = HotspotResult(rank=1, zone_id=1, count=1)
    with pytest.raises(Exception):
        r.rank = 2  # type: ignore[misc]
