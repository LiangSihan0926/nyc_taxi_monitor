"""Experiment 3 — Streaming vs batch hotspot detection.

Feeds one month of trips through a :class:`StreamingMonitor` in mini-batches
and compares its final top-k to the batch-SQL top-k.  They *should* match
exactly (the monitor holds an exact ``dict``) — the real comparison is
**latency**: time-to-first-answer and time-per-batch.
"""
from __future__ import annotations

import argparse
import time
from calendar import monthrange
from pathlib import Path

import pandas as pd

from taxi_monitor.aggregate import busiest_zones
from taxi_monitor.approximate import compare_topk
from taxi_monitor.clean import clean_trips
from taxi_monitor.database import connect
from taxi_monitor.hotspot import HotspotResult
from taxi_monitor.ingest import load_trips
from taxi_monitor.streaming import StreamingMonitor, stream_from_dataframe
from taxi_monitor.utils import DB_PATH, PROJECT_ROOT, RAW_DIR, ensure_dir, get_logger

logger = get_logger("experiment_3")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--month", default="2024-01", help="YYYY-MM of trip file to stream")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=10_000)
    p.add_argument("--raw-dir", default=str(RAW_DIR))
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / "reports"))
    args = p.parse_args()

    out_dir = ensure_dir(args.out_dir)
    path = Path(args.raw_dir) / f"yellow_tripdata_{args.month}.parquet"
    if not path.exists():
        raise SystemExit(f"{path} not found — run scripts/download_data.py first")

    # --- streaming side --------------------------------------------------
    logger.info("loading + cleaning %s for streaming", path.name)
    raw = load_trips(path)
    clean_df, _ = clean_trips(raw)

    monitor = StreamingMonitor()
    stream_iter = stream_from_dataframe(clean_df, batch_size=args.batch_size)
    batch_latencies = []
    t0 = time.perf_counter()
    for i, batch in enumerate(stream_iter):
        bs = time.perf_counter()
        monitor.update_batch(batch)
        batch_latencies.append(time.perf_counter() - bs)
        if i % 25 == 0:
            logger.info(
                "batch %d  ingested=%d  latest_ts=%s",
                i,
                monitor.ingested,
                monitor.latest_ts,
            )
    stream_total = time.perf_counter() - t0

    stream_topk = monitor.top_k(args.k)
    logger.info("streaming done: %.2fs, %d events", stream_total, monitor.ingested)

    # --- batch side (filtered to same month as streaming for fair comparison) -
    year, month = map(int, args.month.split("-"))
    last_day = monthrange(year, month)[1]
    since = f"{args.month}-01 00:00:00"
    until = f"{args.month}-{last_day:02d} 23:59:59"

    logger.info("running batch SQL query on DuckDB (filtered to %s)", args.month)
    conn = connect(args.db)
    try:
        t0 = time.perf_counter()
        batch_df = busiest_zones(conn, k=args.k, since=since, until=until)
        batch_total = time.perf_counter() - t0
    finally:
        conn.close()
    batch_topk = [
        HotspotResult(rank=i + 1, zone_id=int(r.zone_id), count=int(r.trips))
        for i, r in enumerate(batch_df.itertuples(index=False))
    ]

    # --- comparison ------------------------------------------------------
    comparison = compare_topk(batch_topk, stream_topk)
    logger.info("overlap=%d  jaccard=%.3f  rho=%.3f", *comparison.values())

    summary = pd.DataFrame(
        [
            {
                "metric": "stream_total_sec",
                "value": stream_total,
            },
            {"metric": "batch_total_sec", "value": batch_total},
            {"metric": "events", "value": monitor.ingested},
            {
                "metric": "mean_batch_latency_ms",
                "value": 1000 * sum(batch_latencies) / max(len(batch_latencies), 1),
            },
            *[
                {"metric": f"cmp_{k}", "value": v}
                for k, v in comparison.items()
            ],
        ]
    )
    summary.to_csv(out_dir / "experiment_3_summary.csv", index=False)
    logger.info("summary:\n%s", summary)


if __name__ == "__main__":
    main()
