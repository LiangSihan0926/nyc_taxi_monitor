"""Download NYC TLC Yellow Taxi parquet files + zone lookup.

Usage
-----
    python scripts/download_data.py                   # defaults: Nov'23..Jan'24
    python scripts/download_data.py --months 2024-01 2024-02
    python scripts/download_data.py --overwrite
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

from taxi_monitor.ingest import download_yellow_tripdata, download_zone_lookup
from taxi_monitor.utils import RAW_DIR, ensure_dir, get_logger

logger = get_logger("download_data")

# We download these months by default:
#   2023-11, 2023-12 — historical baseline for anomaly detection
#   2024-01          — "current" month we analyse / stream
DEFAULT_MONTHS: List[Tuple[int, int]] = [
    (2023, 11),
    (2023, 12),
    (2024, 1),
]


def parse_month(s: str) -> Tuple[int, int]:
    year, month = s.split("-")
    return int(year), int(month)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        nargs="+",
        metavar="YYYY-MM",
        help="Which months to download (default: 2023-11 2023-12 2024-01)",
    )
    parser.add_argument(
        "--out", default=str(RAW_DIR), help=f"Output dir (default: {RAW_DIR})"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    months = [parse_month(m) for m in args.months] if args.months else DEFAULT_MONTHS
    out_dir = ensure_dir(args.out)

    logger.info("downloading %d months to %s", len(months), out_dir)
    trips = download_yellow_tripdata(months, out_dir=out_dir, overwrite=args.overwrite)
    zones = download_zone_lookup(out_dir=out_dir, overwrite=args.overwrite)

    logger.info("done — %d trip files + 1 zone file", len(trips))
    for p in trips:
        logger.info("  %s  (%d MB)", p.name, Path(p).stat().st_size // (1 << 20))
    logger.info("  %s", zones.name)


if __name__ == "__main__":
    main()
