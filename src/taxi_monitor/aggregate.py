"""Module 2b: Aggregation queries on `clean_trips`.

Every function returns a `pandas.DataFrame` so notebooks / experiments can
continue processing in Python.
"""
from __future__ import annotations

from typing import Optional

import duckdb
import pandas as pd

from .utils import get_logger

__all__ = [
    "zone_hour_demand",
    "zone_daily_demand",
    "busiest_zones",
    "demand_distribution",
    "hourly_totals",
]

logger = get_logger(__name__)


def zone_hour_demand(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Trip count per (pickup_hour, pu_location_id).

    This is the canonical aggregation the rest of the system is built on.
    """
    return conn.execute(
        """
        SELECT pickup_hour,
               pu_location_id AS zone_id,
               COUNT(*)       AS trips
          FROM clean_trips
         GROUP BY pickup_hour, zone_id
         ORDER BY pickup_hour, zone_id
        """
    ).df()


def zone_daily_demand(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute(
        """
        SELECT pickup_date,
               pu_location_id AS zone_id,
               COUNT(*)       AS trips
          FROM clean_trips
         GROUP BY pickup_date, zone_id
         ORDER BY pickup_date, zone_id
        """
    ).df()


def busiest_zones(
    conn: duckdb.DuckDBPyConnection,
    *,
    k: int = 10,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> pd.DataFrame:
    """Return the `k` zones with the highest trip count over the given time
    range (both bounds inclusive, ISO-formatted strings).  Joins zone_lookup
    when it exists so the output is human-readable.
    """
    filters, params = [], []
    if since is not None:
        filters.append("pickup_hour >= ?")
        params.append(since)
    if until is not None:
        filters.append("pickup_hour <= ?")
        params.append(until)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    has_lookup = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='zone_lookup'"
    ).fetchone()[0]

    if has_lookup:
        sql = f"""
            SELECT t.pu_location_id AS zone_id,
                   COALESCE(z.zone, '<unknown>')    AS zone_name,
                   COALESCE(z.borough, '<unknown>') AS borough,
                   COUNT(*)                         AS trips
              FROM clean_trips t
              LEFT JOIN zone_lookup z
                     ON z.location_id = t.pu_location_id
             {where}
             GROUP BY zone_id, zone_name, borough
             ORDER BY trips DESC
             LIMIT ?
        """
    else:
        sql = f"""
            SELECT pu_location_id AS zone_id,
                   COUNT(*)       AS trips
              FROM clean_trips
             {where}
             GROUP BY zone_id
             ORDER BY trips DESC
             LIMIT ?
        """
    params.append(k)
    return conn.execute(sql, params).df()


def demand_distribution(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Distribution stats of hourly demand per zone (for anomaly baselines)."""
    return conn.execute(
        """
        WITH per_hour AS (
            SELECT pu_location_id AS zone_id,
                   pickup_hour,
                   COUNT(*) AS trips
              FROM clean_trips
             GROUP BY zone_id, pickup_hour
        )
        SELECT zone_id,
               COUNT(*)       AS hours_observed,
               AVG(trips)     AS mean_trips,
               STDDEV_POP(trips) AS std_trips,
               MIN(trips)     AS min_trips,
               MAX(trips)     AS max_trips
          FROM per_hour
         GROUP BY zone_id
         ORDER BY mean_trips DESC
        """
    ).df()


def hourly_totals(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Total city-wide trips per pickup_hour — a sanity-check time series."""
    return conn.execute(
        """
        SELECT pickup_hour, COUNT(*) AS trips
          FROM clean_trips
         GROUP BY pickup_hour
         ORDER BY pickup_hour
        """
    ).df()
