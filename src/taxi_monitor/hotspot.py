"""Module 3: Hotspot detection.

Finds the top-k busiest zones in a given time window using a min-heap of size
k.  This is O(n log k) in time and O(k) in memory — strictly better than
full-sorting O(n log n) when n >> k, which is exactly our setting (thousands
of zone/hour cells per window, k typically 5–20).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

import pandas as pd

from .utils import get_logger

__all__ = ["HotspotResult", "top_k_heap", "top_k_from_counts", "top_k_per_window"]

logger = get_logger(__name__)


@dataclass(frozen=True)
class HotspotResult:
    """One (zone, count) pair with a rank (1 = busiest)."""

    rank: int
    zone_id: int
    count: int


def top_k_heap(items: Iterable[Tuple[int, int]], k: int) -> List[HotspotResult]:
    """Return the top-`k` items from an iterable of ``(zone_id, count)`` pairs.

    Uses a bounded min-heap: we keep at most `k` elements, replacing the
    smallest whenever we see a larger count.  Ties are broken by zone_id so
    output is deterministic.
    """
    if k <= 0:
        return []

    heap: List[Tuple[int, int]] = []  # (count, zone_id) — smallest on top
    for zone_id, count in items:
        if count is None:
            continue
        # Negate zone_id so that on a count-tie we *prefer* the *smaller*
        # zone_id (which becomes the larger tuple under heapq's min-heap
        # semantics, hence survives the pop).
        entry = (int(count), -int(zone_id))
        if len(heap) < k:
            heapq.heappush(heap, entry)
        elif entry > heap[0]:
            heapq.heapreplace(heap, entry)

    # Heap contents are unordered — sort once at the end (O(k log k)).
    ordered = sorted(heap, key=lambda t: (-t[0], -t[1]))
    return [
        HotspotResult(rank=i + 1, zone_id=-z, count=c)
        for i, (c, z) in enumerate(ordered)
    ]


def top_k_from_counts(counts: Mapping[int, int], k: int) -> List[HotspotResult]:
    """Convenience wrapper around `top_k_heap` for dict-like count inputs."""
    return top_k_heap(counts.items(), k)


def top_k_per_window(
    demand: pd.DataFrame,
    *,
    k: int = 10,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Apply `top_k_heap` per time window in a demand DataFrame.

    Returns a long-format DataFrame with columns
    ``[window, rank, zone_id, count]``.
    """
    required = {window_col, zone_col, count_col}
    missing = required - set(demand.columns)
    if missing:
        raise ValueError(f"demand DataFrame missing columns: {missing}")

    rows: List[Dict] = []
    # groupby(sort=True) gives deterministic window order.
    for window, group in demand.groupby(window_col, sort=True):
        items = zip(group[zone_col].to_numpy(), group[count_col].to_numpy())
        for res in top_k_heap(items, k):
            rows.append(
                {
                    window_col: window,
                    "rank": res.rank,
                    zone_col: res.zone_id,
                    count_col: res.count,
                }
            )
    return pd.DataFrame(rows, columns=[window_col, "rank", zone_col, count_col])
