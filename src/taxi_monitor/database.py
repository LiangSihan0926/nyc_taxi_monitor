"""Module 2a: SQL storage.

Uses DuckDB because (a) it reads parquet natively with zero setup, (b) it's
columnar and so makes group-by aggregations fast, and (c) it can persist to a
single `.duckdb` file — nice for reproducibility.  The same SQL would work
on SQLite with minor tweaks.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional, Union

import duckdb
import pandas as pd

from .utils import ensure_dir, get_logger

__all__ = [
    "connect",
    "init_schema",
    "insert_clean_trips",
    "insert_zone_lookup",
    "count_rows",
    "table_exists",
    "drop_all",
]

logger = get_logger(__name__)


# --- schema ---------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS zone_lookup (
    location_id   INTEGER PRIMARY KEY,
    borough       VARCHAR,
    zone          VARCHAR,
    service_zone  VARCHAR
);

CREATE TABLE IF NOT EXISTS clean_trips (
    pickup_datetime   TIMESTAMP NOT NULL,
    dropoff_datetime  TIMESTAMP NOT NULL,
    pu_location_id    INTEGER   NOT NULL,
    do_location_id    INTEGER   NOT NULL,
    passenger_count   INTEGER,
    trip_distance     DOUBLE,
    fare_amount       DOUBLE,
    total_amount      DOUBLE,
    trip_duration_sec BIGINT    NOT NULL,
    pickup_hour       TIMESTAMP NOT NULL,
    pickup_date       DATE      NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clean_pickup_hour
    ON clean_trips(pickup_hour);
CREATE INDEX IF NOT EXISTS idx_clean_zone
    ON clean_trips(pu_location_id);
"""


def connect(path: Union[str, Path, None] = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB database.

    Pass ``":memory:"`` or ``None`` for an in-memory db, otherwise a path.
    """
    if path is None or str(path) == ":memory:":
        return duckdb.connect(":memory:")
    path = Path(path)
    ensure_dir(path.parent)
    return duckdb.connect(str(path))


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables and indexes if they don't already exist."""
    conn.execute(SCHEMA_SQL)


@contextmanager
def _temp_register(
    conn: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame
) -> Iterator[None]:
    """Register `df` as a DuckDB view for the duration of the `with` block."""
    conn.register(name, df)
    try:
        yield
    finally:
        conn.unregister(name)


# --- loaders --------------------------------------------------------------

# Mapping from clean-DataFrame columns to SQL columns. Keeping this explicit
# protects us from pandas column-order quirks.
_TRIP_COL_MAP = {
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "PULocationID": "pu_location_id",
    "DOLocationID": "do_location_id",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "fare_amount": "fare_amount",
    "total_amount": "total_amount",
    "trip_duration_sec": "trip_duration_sec",
    "pickup_hour": "pickup_hour",
    "pickup_date": "pickup_date",
}


def insert_clean_trips(
    conn: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    *,
    replace: bool = False,
) -> int:
    """Insert a cleaned trips DataFrame into ``clean_trips``.

    Returns the number of rows inserted.  If `replace=True` the existing rows
    in the table are deleted first.
    """
    if df.empty:
        return 0
    prepared = pd.DataFrame(
        {sql_col: df[src] for src, sql_col in _TRIP_COL_MAP.items() if src in df.columns}
    )
    # Fill optional columns with None so the schema matches exactly.
    for sql_col in _TRIP_COL_MAP.values():
        if sql_col not in prepared.columns:
            prepared[sql_col] = None
    prepared = prepared[list(_TRIP_COL_MAP.values())]

    if replace:
        conn.execute("DELETE FROM clean_trips")

    with _temp_register(conn, "_incoming", prepared):
        conn.execute("INSERT INTO clean_trips SELECT * FROM _incoming")
    logger.info("inserted %s rows into clean_trips", f"{len(prepared):,}")
    return len(prepared)


def insert_zone_lookup(
    conn: duckdb.DuckDBPyConnection, df: pd.DataFrame, *, replace: bool = True
) -> int:
    """Insert a zone-lookup DataFrame into ``zone_lookup``."""
    prepared = pd.DataFrame(
        {
            "location_id": df["LocationID"].astype(int),
            "borough": df["Borough"].astype(str),
            "zone": df["Zone"].astype(str),
            "service_zone": df["service_zone"].astype(str),
        }
    )
    if replace:
        conn.execute("DELETE FROM zone_lookup")
    with _temp_register(conn, "_zones", prepared):
        conn.execute("INSERT INTO zone_lookup SELECT * FROM _zones")
    return len(prepared)


# --- tiny helpers ---------------------------------------------------------


def table_exists(conn: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [name],
    ).fetchone()
    return bool(row and row[0])


def count_rows(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def drop_all(conn: duckdb.DuckDBPyConnection, tables: Optional[Iterable[str]] = None) -> None:
    """Drop project tables (useful for re-running the pipeline cleanly)."""
    tables = tables or ("clean_trips", "zone_lookup")
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
