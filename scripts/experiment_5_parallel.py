"""Experiment 5 — MapReduce-style parallel ingest.

Benchmarks the ``taxi_monitor.parallel`` map-reduce across a sweep of
worker counts (``--workers 1 2 4 8`` by default).  Each run reads,
cleans, and zone-counts every downloaded monthly parquet in parallel,
then reduces per-worker counts into a single global top-k via a
bounded heap.

The first worker count is treated as the sequential baseline and the
``speedup`` column is computed against it.

Output: ``reports/experiment_5_parallel.csv``
"""
from __future__ import annotations

import argparse
from pathlib import Path

from taxi_monitor.parallel import benchmark
from taxi_monitor.utils import PROJECT_ROOT, RAW_DIR, ensure_dir, get_logger

logger = get_logger("experiment_5")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", default=str(RAW_DIR))
    p.add_argument("--k", type=int, default=10)
    p.add_argument(
        "--workers",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8],
        help="Worker counts to benchmark (first entry is the baseline).",
    )
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "reports"))
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    paths = sorted(Path(args.raw_dir).glob("yellow_tripdata_*.parquet"))
    if not paths:
        raise SystemExit(
            f"No parquet files in {args.raw_dir} — run scripts/download_data.py first"
        )
    logger.info("benchmarking on %d files: %s",
                len(paths), [p.name for p in paths])

    df = benchmark(paths, k=args.k, worker_counts=args.workers)
    out = Path(out_dir) / "experiment_5_parallel.csv"
    df.to_csv(out, index=False)
    logger.info("\n%s", df.to_string(index=False))
    logger.info("wrote %s", out)


if __name__ == "__main__":
    main()
