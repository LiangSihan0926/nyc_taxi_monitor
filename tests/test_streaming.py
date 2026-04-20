"""Tests for taxi_monitor.streaming."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from taxi_monitor.streaming import StreamingMonitor, stream_from_dataframe


def test_streaming_cumulative_counts():
    m = StreamingMonitor()
    for ts, zone in [("2024-01-01 00:00", 1), ("2024-01-01 00:01", 1), ("2024-01-01 00:02", 2)]:
        m.update(pd.Timestamp(ts), zone)
    counts = m.counts()
    assert counts == {1: 2, 2: 1}
    assert m.ingested == 3
    assert m.latest_ts == pd.Timestamp("2024-01-01 00:02")


def test_streaming_top_k():
    m = StreamingMonitor()
    events = [(pd.Timestamp("2024-01-01"), z) for z in [1, 1, 1, 2, 2, 3]]
    m.update_batch(events)
    top = m.top_k(2)
    assert [r.zone_id for r in top] == [1, 2]


def test_streaming_sliding_window_evicts():
    m = StreamingMonitor(window=timedelta(minutes=5))
    base = pd.Timestamp("2024-01-01 00:00")

    # Minute 0..4: zone 1 (5 events)
    for i in range(5):
        m.update(base + pd.Timedelta(minutes=i), 1)
    # Minute 10: zone 2 — this should evict all zone-1 events.
    m.update(base + pd.Timedelta(minutes=10), 2)

    cumulative = m.counts()
    assert cumulative == {1: 5, 2: 1}
    windowed = m.window_counts()
    assert windowed == {2: 1}

    top = m.top_k(2, windowed=True)
    assert len(top) == 1
    assert top[0].zone_id == 2


def test_window_counts_empty_when_disabled():
    m = StreamingMonitor()
    m.update(pd.Timestamp("2024-01-01"), 1)
    assert m.window_counts() == {}


def test_snapshot_shape():
    m = StreamingMonitor(window=timedelta(minutes=1))
    m.update(pd.Timestamp("2024-01-01"), 1)
    snap = m.snapshot()
    assert snap["ingested"] == 1
    assert snap["unique_zones"] == 1
    assert snap["window_seconds"] == 60.0
    assert snap["window_events"] == 1


def test_len_returns_ingested():
    m = StreamingMonitor()
    m.update_batch([(pd.Timestamp("2024-01-01"), 1)] * 7)
    assert len(m) == 7


def test_stream_from_dataframe_sorts_and_batches(raw_trips_df):
    batches = list(
        stream_from_dataframe(
            raw_trips_df.sample(frac=1, random_state=0),
            batch_size=25,
        )
    )
    flat = [e for b in batches for e in b]
    assert len(flat) == len(raw_trips_df)
    times = [t for t, _ in flat]
    assert times == sorted(times)
    # Last batch may be smaller; all other batches exactly 25.
    assert all(len(b) == 25 for b in batches[:-1])


def test_stream_from_dataframe_validation(raw_trips_df):
    with pytest.raises(KeyError):
        next(stream_from_dataframe(raw_trips_df, ts_col="nope"))
    with pytest.raises(ValueError):
        next(stream_from_dataframe(raw_trips_df, batch_size=0))


def test_earlier_ts_does_not_move_latest_backwards():
    m = StreamingMonitor()
    m.update(pd.Timestamp("2024-01-01 10:00"), 1)
    m.update(pd.Timestamp("2024-01-01 09:00"), 2)  # late arrival
    assert m.latest_ts == pd.Timestamp("2024-01-01 10:00")
