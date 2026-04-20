"""Module 4: Anomaly / demand-surge detection.

For every zone we compute a baseline (historical mean and std of hourly
trip-count), then flag *current* hours whose z-score exceeds a threshold.

Design choices
--------------
* Baseline is computed **per (zone, hour-of-week)** by default.  Raw per-zone
  means would confuse weekday rush-hour with weekend dead-time; the hour-of-
  week split (0..167) captures weekly seasonality cheaply without needing a
  full ARIMA / Prophet model.
* Zones whose baseline std is zero (or almost zero) are ignored — z-score is
  undefined there and they're usually empty zones anyway.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .utils import get_logger

__all__ = ["BaselineStats", "fit_baseline", "z_scores", "detect_anomalies"]

logger = get_logger(__name__)


@dataclass
class BaselineStats:
    """Per-(zone, hour-of-week) mean/std of trip counts.

    Stored as a DataFrame with columns ``[zone_id, hour_of_week, mean, std, n]``.
    """

    table: pd.DataFrame

    def lookup(self, zone_id: int, hour_of_week: int) -> Optional[tuple]:
        rows = self.table[
            (self.table["zone_id"] == zone_id)
            & (self.table["hour_of_week"] == hour_of_week)
        ]
        if rows.empty:
            return None
        r = rows.iloc[0]
        return float(r["mean"]), float(r["std"]), int(r["n"])


def _hour_of_week(series: pd.Series) -> pd.Series:
    """Map a datetime series to 0..167 (Monday 00:00 = 0)."""
    dt = pd.to_datetime(series)
    return (dt.dt.dayofweek * 24 + dt.dt.hour).astype(int)


def fit_baseline(
    demand: pd.DataFrame,
    *,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> BaselineStats:
    """Compute baseline mean/std per (zone, hour-of-week).

    `demand` should be the output of
    :func:`taxi_monitor.aggregate.zone_hour_demand`.
    """
    df = demand.copy()
    df["hour_of_week"] = _hour_of_week(df[window_col])
    grouped = df.groupby([zone_col, "hour_of_week"])[count_col]
    stats = grouped.agg(
        mean="mean", std=lambda x: float(np.std(x, ddof=0)), n="count"
    ).reset_index()
    return BaselineStats(table=stats)


def z_scores(
    demand: pd.DataFrame,
    baseline: BaselineStats,
    *,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
    min_std: float = 1.0,
) -> pd.DataFrame:
    """Attach a ``z`` column to `demand` using `baseline`.

    Rows whose baseline std is below `min_std` get ``z = NaN`` — we refuse to
    flag anomalies on vanishingly small baselines (they produce huge spurious
    z's).  `min_std=1.0` is a defensible default for integer trip counts.
    """
    df = demand.copy()
    df["hour_of_week"] = _hour_of_week(df[window_col])
    merged = df.merge(
        baseline.table, on=[zone_col, "hour_of_week"], how="left", suffixes=("", "_bl")
    )

    mean = merged["mean"]
    std = merged["std"].where(merged["std"] >= min_std)
    merged["z"] = (merged[count_col] - mean) / std
    # Explicitly preserve the original columns plus the new ones.
    return merged[
        [window_col, zone_col, count_col, "hour_of_week", "mean", "std", "z"]
    ]


def detect_anomalies(
    demand: pd.DataFrame,
    baseline: BaselineStats,
    *,
    threshold: float = 3.0,
    **kwargs,
) -> pd.DataFrame:
    """Return only the rows whose absolute z-score exceeds `threshold`.

    Keyword arguments are forwarded to :func:`z_scores`.
    """
    scored = z_scores(demand, baseline, **kwargs)
    flagged = scored.loc[scored["z"].abs() >= threshold].copy()
    flagged = flagged.sort_values("z", ascending=False).reset_index(drop=True)
    logger.info(
        "anomalies: %d / %d rows exceed |z| >= %.1f",
        len(flagged),
        len(scored),
        threshold,
    )
    return flagged
