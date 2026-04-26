"""Higher-level SQL analytics / business questions on top of ``clean_trips``.

These queries are aimed at making the project feel more like an operations
analytics system, not just a benchmark harness.
"""
from __future__ import annotations

from typing import Optional

import duckdb
import pandas as pd

from .utils import get_logger

__all__ = [
    "weekday_weekend_demand",
    "airport_vs_manhattan",
    "top_origin_destination_pairs",
    "borough_flow_matrix",
    "zone_hour_heatmap",
    "avg_fare_distance_by_zone",
]

logger = get_logger(__name__)


def weekday_weekend_demand(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Compare weekday vs weekend hourly demand."""
    return conn.execute(
        """
        SELECT
            CASE WHEN EXTRACT(ISODOW FROM pickup_datetime) IN (6, 7)
                 THEN 'weekend' ELSE 'weekday' END AS day_type,
            EXTRACT(HOUR FROM pickup_datetime) AS hour_of_day,
            COUNT(*) AS trips
        FROM clean_trips
        GROUP BY day_type, hour_of_day
        ORDER BY day_type, hour_of_day
        """
    ).df()


def airport_vs_manhattan(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Demand comparison for airport zones versus Manhattan zones.

    Requires ``zone_lookup`` to be present.
    """
    return conn.execute(
        """
        SELECT
            CASE
                WHEN lower(z.zone) LIKE '%jfk%' OR lower(z.zone) LIKE '%la guardia%'
                    THEN 'airport'
                WHEN z.borough = 'Manhattan'
                    THEN 'manhattan'
                ELSE 'other'
            END AS segment,
            DATE_TRUNC('day', t.pickup_datetime) AS pickup_day,
            COUNT(*) AS trips,
            AVG(t.trip_distance) AS avg_distance,
            AVG(t.fare_amount) AS avg_fare
        FROM clean_trips t
        LEFT JOIN zone_lookup z ON z.location_id = t.pu_location_id
        GROUP BY segment, pickup_day
        ORDER BY pickup_day, segment
        """
    ).df()


def top_origin_destination_pairs(
    conn: duckdb.DuckDBPyConnection,
    *,
    k: int = 20,
    min_trip_distance: float = 0.5,
) -> pd.DataFrame:
    """Top pickup→dropoff pairs by trip count."""
    return conn.execute(
        """
        SELECT
            pu_location_id AS origin_zone_id,
            do_location_id AS destination_zone_id,
            COUNT(*) AS trips,
            AVG(trip_distance) AS avg_distance,
            AVG(total_amount) AS avg_total_amount
        FROM clean_trips
        WHERE trip_distance >= ?
        GROUP BY origin_zone_id, destination_zone_id
        ORDER BY trips DESC
        LIMIT ?
        """,
        [min_trip_distance, k],
    ).df()


def borough_flow_matrix(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Inter-borough trip flows (pickup borough -> dropoff borough)."""
    return conn.execute(
        """
        SELECT
            COALESCE(pu.borough, 'Unknown') AS origin_borough,
            COALESCE(doz.borough, 'Unknown') AS destination_borough,
            COUNT(*) AS trips
        FROM clean_trips t
        LEFT JOIN zone_lookup pu  ON pu.location_id  = t.pu_location_id
        LEFT JOIN zone_lookup doz ON doz.location_id = t.do_location_id
        GROUP BY origin_borough, destination_borough
        ORDER BY trips DESC, origin_borough, destination_borough
        """
    ).df()


def zone_hour_heatmap(
    conn: duckdb.DuckDBPyConnection,
    *,
    top_k_zones: int = 20,
) -> pd.DataFrame:
    """Matrix-ready heatmap table for the busiest zones across hour-of-day."""
    return conn.execute(
        """
        WITH top_zones AS (
            SELECT
                pu_location_id AS zone_id,
                COUNT(*) AS trips
            FROM clean_trips
            GROUP BY pu_location_id
            ORDER BY trips DESC
            LIMIT ?
        )
        SELECT
            t.pu_location_id AS zone_id,
            EXTRACT(HOUR FROM t.pickup_datetime) AS hour_of_day,
            COUNT(*) AS trips
        FROM clean_trips t
        INNER JOIN top_zones z
            ON z.zone_id = t.pu_location_id
        GROUP BY
            t.pu_location_id,
            EXTRACT(HOUR FROM t.pickup_datetime)
        ORDER BY
            t.pu_location_id,
            EXTRACT(HOUR FROM t.pickup_datetime)
        """,
        [top_k_zones],
    ).df()


def avg_fare_distance_by_zone(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Business-oriented zone summary for demand, fare, and distance."""
    return conn.execute(
        """
        SELECT
            t.pu_location_id AS zone_id,
            COALESCE(z.zone, '') AS zone_name,
            COALESCE(z.borough, '') AS borough,
            COUNT(*) AS trips,
            AVG(t.trip_distance) AS avg_distance,
            AVG(t.fare_amount) AS avg_fare,
            AVG(t.total_amount) AS avg_total_amount,
            AVG(t.trip_duration_sec) / 60.0 AS avg_duration_min
        FROM clean_trips t
        LEFT JOIN zone_lookup z
            ON z.location_id = t.pu_location_id
        GROUP BY
            t.pu_location_id,
            COALESCE(z.zone, ''),
            COALESCE(z.borough, '')
        ORDER BY trips DESC
        """
    ).df()
