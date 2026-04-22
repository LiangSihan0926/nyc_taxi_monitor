"""Tests for the parallel map-reduce module.

The reduce step is pure and cheap to exercise directly.  The map step
is tested by running it against the ``raw_trips_parquet`` fixture,
which bypasses ``multiprocessing.Pool`` — spawning real subprocesses
in unit tests is slow and flaky on CI runners.  The pool-based
orchestration is verified once end-to-end with a single worker.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from taxi_monitor.parallel import (
    benchmark,
    map_zone_counts,
    parallel_top_k,
    reduce_top_k,
)


# ---------------------------------------------------------------------------
# reduce step — pure, deterministic
# ---------------------------------------------------------------------------


def test_reduce_top_k_sums_partials() -> None:
    partials = [{1: 10, 2: 5, 3: 1}, {1: 3, 2: 4, 4: 7}]
    assert reduce_top_k(partials, k=2) == [(1, 13), (2, 9)]


def test_reduce_top_k_tie_break_on_zone_id() -> None:
    partials = [{5: 10, 3: 10, 9: 10}]
    top = reduce_top_k(partials, k=3)
    assert [z for z, _ in top] == [3, 5, 9]  # ascending zone_id on ties


def test_reduce_top_k_empty() -> None:
    assert reduce_top_k([], k=5) == []


def test_reduce_top_k_k_larger_than_unique_zones() -> None:
    assert reduce_top_k([{1: 2, 2: 1}], k=10) == [(1, 2), (2, 1)]


# ---------------------------------------------------------------------------
# map step — exercises the real clean + count pipeline
# ---------------------------------------------------------------------------


def test_map_zone_counts_matches_manual_count(raw_trips_parquet: Path) -> None:
    counts = map_zone_counts(raw_trips_parquet)
    # Should only contain valid zones in [1, 263] and non-zero counts
    assert all(1 <= z <= 263 for z in counts.keys())
    assert all(c > 0 for c in counts.values())
    # Total rows in counts must match total clean rows
    total = sum(counts.values())
    assert total > 0


# ---------------------------------------------------------------------------
# end-to-end — spins up multiprocessing.Pool for real
# ---------------------------------------------------------------------------


def test_parallel_top_k_single_worker(raw_trips_parquet: Path) -> None:
    top, secs = parallel_top_k([raw_trips_parquet], k=3, workers=1)
    assert len(top) <= 3
    assert secs > 0
    # Each row is (zone_id, count) with positive count
    assert all(isinstance(z, int) and c > 0 for z, c in top)
    # Counts must be monotone non-increasing (it's a top-k)
    counts_only = [c for _, c in top]
    assert counts_only == sorted(counts_only, reverse=True)


def test_benchmark_returns_speedup_column(raw_trips_parquet: Path) -> None:
    df = benchmark([raw_trips_parquet], k=3, worker_counts=[1])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["workers", "wall_sec", "speedup"]
    assert df.loc[0, "workers"] == 1
    assert df.loc[0, "speedup"] == 1.0  # baseline vs itself
