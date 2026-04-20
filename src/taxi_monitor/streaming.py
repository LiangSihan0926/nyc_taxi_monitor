"""Extension 1: Online / streaming hotspot monitor.

A single class — :class:`StreamingMonitor` — consumes trips one-by-one (or in
mini-batches) and maintains:

* an exact per-zone count (``dict``),
* a sliding window of recent events (``deque``) so we can also expose
  "demand in the last N minutes",
* an on-demand top-k view (computed via :func:`taxi_monitor.hotspot.top_k_heap`).

The monitor is intentionally pure-Python so it can be reasoned about in tests
and used outside DuckDB (e.g. fed from a Kafka consumer in a real system).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, Iterable, Iterator, List, Optional, Tuple, Union

import pandas as pd

from .hotspot import HotspotResult, top_k_from_counts
from .utils import get_logger

__all__ = ["StreamingEvent", "StreamingMonitor", "stream_from_dataframe"]

logger = get_logger(__name__)

TimeLike = Union[datetime, pd.Timestamp]


@dataclass(frozen=True)
class StreamingEvent:
    """One trip arriving at the monitor."""

    ts: pd.Timestamp
    zone_id: int


@dataclass
class StreamingMonitor:
    """Online zone-demand monitor.

    Parameters
    ----------
    window : timedelta, optional
        If given, `window_counts()` returns demand restricted to the last
        `window` of wall-clock time (based on the *event time* of the latest
        ingested event, not the system clock).  If None, only cumulative
        counts are tracked and the sliding-window deque is disabled.
    """

    window: Optional[timedelta] = None
    _counts: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    _events: Deque[StreamingEvent] = field(default_factory=deque)
    _window_counts: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    _latest: Optional[pd.Timestamp] = None
    _ingested: int = 0

    # --- ingestion -------------------------------------------------------

    def update(self, ts: TimeLike, zone_id: int) -> None:
        """Ingest one event (timestamp, zone_id)."""
        ts = pd.Timestamp(ts)
        zone_id = int(zone_id)
        self._counts[zone_id] += 1
        self._ingested += 1
        self._latest = (
            ts if self._latest is None or ts > self._latest else self._latest
        )

        if self.window is not None:
            self._events.append(StreamingEvent(ts=ts, zone_id=zone_id))
            self._window_counts[zone_id] += 1
            self._evict_old()

    def update_batch(self, events: Iterable[Tuple[TimeLike, int]]) -> int:
        """Ingest a batch of ``(ts, zone_id)`` tuples.  Returns batch size."""
        n = 0
        for ts, zone_id in events:
            self.update(ts, zone_id)
            n += 1
        return n

    # --- internal --------------------------------------------------------

    def _evict_old(self) -> None:
        """Pop events that have fallen out of the sliding window."""
        if self.window is None or self._latest is None:
            return
        cutoff = self._latest - self.window
        while self._events and self._events[0].ts < cutoff:
            old = self._events.popleft()
            self._window_counts[old.zone_id] -= 1
            if self._window_counts[old.zone_id] <= 0:
                # Keep the dict clean so top_k enumerates fewer entries.
                del self._window_counts[old.zone_id]

    # --- queries ---------------------------------------------------------

    @property
    def ingested(self) -> int:
        return self._ingested

    @property
    def latest_ts(self) -> Optional[pd.Timestamp]:
        return self._latest

    def counts(self) -> Dict[int, int]:
        """Return a *copy* of the cumulative zone→count mapping."""
        return dict(self._counts)

    def window_counts(self) -> Dict[int, int]:
        """Counts restricted to the sliding window (empty dict if disabled)."""
        if self.window is None:
            return {}
        self._evict_old()
        return dict(self._window_counts)

    def top_k(self, k: int = 10, *, windowed: bool = False) -> List[HotspotResult]:
        """Top-`k` busiest zones from either the cumulative or windowed view."""
        src = self.window_counts() if windowed else self._counts
        return top_k_from_counts(src, k)

    # --- introspection ---------------------------------------------------

    def __len__(self) -> int:  # total ingested events
        return self._ingested

    def snapshot(self) -> Dict:
        """Dict representation useful for tests and JSON serialization."""
        return {
            "ingested": self._ingested,
            "latest_ts": None if self._latest is None else self._latest.isoformat(),
            "unique_zones": len(self._counts),
            "window_seconds": (
                self.window.total_seconds() if self.window is not None else None
            ),
            "window_events": len(self._events),
        }


# --- helpers --------------------------------------------------------------


def stream_from_dataframe(
    df: pd.DataFrame,
    *,
    ts_col: str = "tpep_pickup_datetime",
    zone_col: str = "PULocationID",
    batch_size: int = 1,
) -> Iterator[List[Tuple[pd.Timestamp, int]]]:
    """Yield batches of ``(ts, zone_id)`` tuples from a sorted DataFrame.

    The DataFrame is first sorted by `ts_col` so events arrive in event-time
    order, matching what a real-world stream would look like.
    """
    if ts_col not in df.columns or zone_col not in df.columns:
        raise KeyError(f"df must contain {ts_col} and {zone_col}")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    ordered = df[[ts_col, zone_col]].sort_values(ts_col).reset_index(drop=True)
    n = len(ordered)
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        batch = list(
            zip(ordered[ts_col].iloc[start:end], ordered[zone_col].iloc[start:end])
        )
        yield batch
