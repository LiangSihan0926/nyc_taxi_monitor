"""Module 1a: Data ingestion.

Downloads NYC TLC Yellow Taxi parquet files and the taxi-zone lookup CSV,
then provides loaders that return tidy `pandas.DataFrame`s.

The TLC hosts the files on CloudFront under a stable URL pattern::

    https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet
    https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv

(NYC TLC site: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

import pandas as pd

from .utils import RAW_DIR, ensure_dir, get_logger

__all__ = [
    "TLC_CLOUDFRONT",
    "ZONE_LOOKUP_URL",
    "tlc_url",
    "download_file",
    "download_yellow_tripdata",
    "download_zone_lookup",
    "load_trips",
    "load_zone_lookup",
]

logger = get_logger(__name__)

TLC_CLOUDFRONT = "https://d37ci6vzurychx.cloudfront.net/trip-data"
ZONE_LOOKUP_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"


def tlc_url(year: int, month: int, taxi_type: str = "yellow") -> str:
    """Return the canonical download URL for a given TLC month."""
    if not (1 <= month <= 12):
        raise ValueError(f"month must be in 1..12, got {month}")
    return f"{TLC_CLOUDFRONT}/{taxi_type}_tripdata_{year:04d}-{month:02d}.parquet"


def download_file(
    url: str,
    dest: Union[str, Path],
    *,
    overwrite: bool = False,
    chunk_size: int = 1 << 20,
) -> Path:
    """Stream-download `url` to `dest`.  Skips download if file already exists
    and `overwrite` is False.
    """
    import requests  # local import keeps import-time deps minimal

    dest = Path(dest)
    ensure_dir(dest.parent)
    if dest.exists() and not overwrite:
        logger.info("skip download (exists): %s", dest.name)
        return dest

    logger.info("downloading %s -> %s", url, dest)
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
    return dest


def download_yellow_tripdata(
    months: Iterable[tuple],
    out_dir: Union[str, Path] = RAW_DIR,
    *,
    overwrite: bool = False,
) -> List[Path]:
    """Download every (year, month) tuple.  Returns the local file paths."""
    out_dir = ensure_dir(out_dir)
    paths: List[Path] = []
    for year, month in months:
        url = tlc_url(year, month)
        dest = out_dir / f"yellow_tripdata_{year:04d}-{month:02d}.parquet"
        paths.append(download_file(url, dest, overwrite=overwrite))
    return paths


def download_zone_lookup(
    out_dir: Union[str, Path] = RAW_DIR,
    *,
    overwrite: bool = False,
) -> Path:
    out_dir = ensure_dir(out_dir)
    return download_file(
        ZONE_LOOKUP_URL, out_dir / "taxi_zone_lookup.csv", overwrite=overwrite
    )


# --- loaders --------------------------------------------------------------

#: Columns we keep from the raw Yellow Taxi parquet.  Everything else is dropped
#: on ingest to keep downstream memory usage small.
YELLOW_COLUMNS = [
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "PULocationID",
    "DOLocationID",
    "fare_amount",
    "total_amount",
]


def load_trips(
    path: Union[str, Path],
    *,
    columns: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Load a Yellow Taxi parquet file, keeping only the columns we care about.

    Unknown columns in `columns` are silently dropped if the source file does
    not have them (so the same code path works on synthetic test fixtures).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    wanted = list(columns) if columns is not None else YELLOW_COLUMNS

    # Discover the real column set first so we can ignore missing columns
    # gracefully. pyarrow reads only the footer, so this is cheap.
    import pyarrow.parquet as pq

    schema_cols = set(pq.ParquetFile(path).schema.names)
    use_cols = [c for c in wanted if c in schema_cols]
    df = pd.read_parquet(path, columns=use_cols or None)
    logger.info("loaded %s rows from %s", f"{len(df):,}", path.name)
    return df


def load_zone_lookup(path: Union[str, Path]) -> pd.DataFrame:
    """Load the taxi_zone_lookup.csv into a DataFrame keyed by LocationID."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    expected = {"LocationID", "Borough", "Zone", "service_zone"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"zone lookup missing columns: {missing}")
    return df
