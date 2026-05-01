"""Module: Parallel map-reduce aggregation.

Processes multiple monthly parquet files concurrently using
``multiprocessing.Pool`` and combines their zone-level trip counts into a
single global top-k via heap-based reduction.  This is a classic
MapReduce pattern:

    map     : parquet_path -> Dict[zone_id, trip_count]
    shuffle : (implicit — each worker emits its own dict)
    reduce  : merge dicts + heapq.nlargest(k)

Each worker runs in its own Python interpreter, side-stepping the GIL
and isolating pandas / pyarrow memory.  For 3 months of TLC data on a
multi-core laptop this is consistently faster than the sequential
baseline; the exact speed-up depends on disk bandwidth and worker
count (see ``scripts/experiment_5_parallel.py``).
"""
from __future__ import annotations

import heapq
import multiprocessing as mp
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

from .clean import clean_trips
from .ingest import load_trips
from .utils import get_logger

__all__ = [
    "map_zone_counts",
    "reduce_top_k",
    "parallel_top_k",
    "benchmark",
]

logger = get_logger(__name__)


def map_zone_counts(path: str | Path) -> Dict[int, int]:
    """Worker — map step for a single parquet file.

    Must be a top-level, picklable function so ``multiprocessing.Pool``
    can dispatch it.  Runs the same deterministic ``clean_trips`` as
    the batch pipeline, then counts trips per pickup zone.
    """
    raw = load_trips(Path(path))
    clean_df, _ = clean_trips(raw)
    counts = clean_df["PULocationID"].value_counts().to_dict()
    return {int(z): int(c) for z, c in counts.items()}


def reduce_top_k(
    partials: Iterable[Dict[int, int]], k: int = 10
) -> List[Tuple[int, int]]:
    """Reduce — sum per-file counts, return global top-k.

    Ties are broken on ascending ``zone_id`` so the result is
    deterministic across runs and matches the convention used by
    ``hotspot.py``.
    """
    total: Counter = Counter()
    for part in partials:
        total.update(part)
    return heapq.nlargest(k, total.items(), key=lambda zc: (zc[1], -zc[0]))


def parallel_top_k(
    paths: List[Path],
    *,
    k: int = 10,
    workers: int | None = None,
) -> Tuple[List[Tuple[int, int]], float]:
    """End-to-end parallel map-reduce.

    Returns ``(top_k, wall_seconds)``.  ``workers`` defaults to
    ``multiprocessing.cpu_count()``.
    """
    workers = workers or mp.cpu_count()
    t0 = time.perf_counter()
    with mp.Pool(processes=workers) as pool:
        partials = pool.map(map_zone_counts, [str(p) for p in paths])
    top_k = reduce_top_k(partials, k=k)
    return top_k, time.perf_counter() - t0


def benchmark(
    paths: List[Path],
    *,
    k: int = 10,
    worker_counts: Iterable[int] = (1, 2, 4),
) -> pd.DataFrame:
    """Run the map-reduce at several worker counts and report speed-up.

    The first entry in ``worker_counts`` is used as the baseline for
    the ``speedup`` column.

    .. note::
       Worker counts are run in the order supplied.  Because reading the
       same parquet files repeatedly warms the OS file cache, later runs
       can be artificially faster than the first.  For rigorous numbers
       randomize ``worker_counts`` or run the sweep multiple times and
       average; the committed CSV uses the natural ascending order, so
       its higher worker counts likely benefit from cache effects.
    """
    rows = []
    for w in worker_counts:
        _, secs = parallel_top_k(paths, k=k, workers=w)
        rows.append({"workers": w, "wall_sec": round(secs, 3)})
        logger.info("workers=%d wall=%.3fs", w, secs)
    df = pd.DataFrame(rows)
    df["speedup"] = (df["wall_sec"].iloc[0] / df["wall_sec"]).round(2)
    return df
