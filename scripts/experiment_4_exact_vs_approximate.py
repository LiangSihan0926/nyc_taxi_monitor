"""Experiment 4 — Exact vs Approximate counting.

For the same stream of pickups from one month, compare three accumulators:

  * exact ``dict`` — baseline
  * :class:`ReservoirSampler` — uniform random sample, reconstructed counts
  * :class:`CountMinSketch` — sublinear frequency estimator

We measure memory, runtime, and top-k accuracy (overlap / Spearman ρ).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict

import pandas as pd

from taxi_monitor.approximate import CountMinSketch, ReservoirSampler, compare_topk
from taxi_monitor.clean import clean_trips
from taxi_monitor.hotspot import top_k_from_counts
from taxi_monitor.ingest import load_trips
from taxi_monitor.utils import PROJECT_ROOT, RAW_DIR, ensure_dir, get_logger

logger = get_logger("experiment_4")


def _dict_memory_bytes(d: Dict[int, int]) -> int:
    """Rough memory estimate for a {int: int} dict."""
    base = sys.getsizeof(d)
    per_entry = sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in d.items())
    return base + per_entry


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--month", default="2024-01")
    p.add_argument("--raw-dir", default=str(RAW_DIR))
    p.add_argument("--reservoir-size", type=int, default=100_000)
    p.add_argument("--cms-width", type=int, default=2048)
    p.add_argument("--cms-depth", type=int, default=5)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "reports"))
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    path = Path(args.raw_dir) / f"yellow_tripdata_{args.month}.parquet"
    if not path.exists():
        raise SystemExit(f"{path} not found — run scripts/download_data.py first")

    raw = load_trips(path, columns=["tpep_pickup_datetime", "tpep_dropoff_datetime",
                                    "PULocationID", "DOLocationID", "trip_distance",
                                    "fare_amount"])
    clean_df, _ = clean_trips(raw)
    zones = clean_df["PULocationID"].astype(int).tolist()
    n = len(zones)
    logger.info("stream length = %d events", n)

    # --- exact ----------------------------------------------------------
    exact: Dict[int, int] = {}
    t0 = time.perf_counter()
    for z in zones:
        exact[z] = exact.get(z, 0) + 1
    exact_time = time.perf_counter() - t0
    exact_mem = _dict_memory_bytes(exact)
    exact_topk = top_k_from_counts(exact, args.k)

    # --- reservoir ------------------------------------------------------
    res = ReservoirSampler(k=args.reservoir_size)
    t0 = time.perf_counter()
    res.add_many(zones)
    res_time = time.perf_counter() - t0
    res_mem = sys.getsizeof(res._reservoir) + sum(
        sys.getsizeof(x) for x in res._reservoir
    )
    res_topk = res.top_k(args.k)

    # --- count-min ------------------------------------------------------
    cms = CountMinSketch(width=args.cms_width, depth=args.cms_depth)
    t0 = time.perf_counter()
    cms.add_many(zones)
    cms_time = time.perf_counter() - t0
    cms_mem = cms.memory_bytes()
    # Candidate set = all unique zones observed; in real systems you'd
    # maintain a separate cheap heavy-hitters sketch, but for NYC zones
    # the universe is only 263 IDs.
    cms_topk = cms.top_k(sorted(set(zones)), args.k)

    # --- report ---------------------------------------------------------
    rows = []
    for label, topk, secs, mem in [
        ("exact_dict", exact_topk, exact_time, exact_mem),
        ("reservoir", res_topk, res_time, res_mem),
        ("count_min_sketch", cms_topk, cms_time, cms_mem),
    ]:
        cmp = compare_topk(exact_topk, topk)
        rows.append(
            {
                "method": label,
                "runtime_sec": secs,
                "memory_bytes": mem,
                "memory_kb": mem / 1024,
                "overlap_with_exact": cmp["overlap"],
                "jaccard": cmp["jaccard"],
                "rank_corr": cmp["rank_correlation"],
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "experiment_4_summary.csv", index=False)
    logger.info("summary:\n%s", df)

    # Also save each top-k for qualitative inspection.
    for label, topk in [
        ("exact", exact_topk),
        ("reservoir", res_topk),
        ("count_min", cms_topk),
    ]:
        pd.DataFrame(
            [
                {"rank": r.rank, "zone_id": r.zone_id, "count": r.count}
                for r in topk
            ]
        ).to_csv(out_dir / f"experiment_4_topk_{label}.csv", index=False)


if __name__ == "__main__":
    main()
