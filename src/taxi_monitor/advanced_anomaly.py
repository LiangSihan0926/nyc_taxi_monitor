"""Stronger anomaly detection variants for hourly taxi demand.

This module complements ``taxi_monitor.anomaly`` by adding more robust baselines:

* robust z-score using median + MAD
* exponentially weighted residual score (EWMA baseline)
* consensus detection across methods
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .forecast import prepare_hourly_panel
from .utils import get_logger

__all__ = [
    "RobustBaselineStats",
    "fit_robust_baseline",
    "robust_z_scores",
    "ewma_residual_scores",
    "detect_consensus_anomalies",
]

logger = get_logger(__name__)


@dataclass(frozen=True)
class RobustBaselineStats:
    table: pd.DataFrame


def _hour_of_week(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series)
    return (dt.dt.dayofweek * 24 + dt.dt.hour).astype(int)


def fit_robust_baseline(
    demand: pd.DataFrame,
    *,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> RobustBaselineStats:
    """Compute per-(zone, hour-of-week) median and MAD."""
    df = demand[[window_col, zone_col, count_col]].copy()
    df["hour_of_week"] = _hour_of_week(df[window_col])

    def _mad(x: pd.Series) -> float:
        med = float(np.median(x))
        return float(np.median(np.abs(x - med)))

    stats = (
        df.groupby([zone_col, "hour_of_week"])[count_col]
        .agg(median="median", mad=_mad, n="count")
        .reset_index()
    )
    return RobustBaselineStats(table=stats)


def robust_z_scores(
    demand: pd.DataFrame,
    baseline: RobustBaselineStats,
    *,
    min_mad: float = 1.0,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Attach robust z-scores based on median/MAD.

    Uses the standard normal consistency factor 1.4826.
    """
    df = demand[[window_col, zone_col, count_col]].copy()
    df["hour_of_week"] = _hour_of_week(df[window_col])
    merged = df.merge(baseline.table, on=[zone_col, "hour_of_week"], how="left")
    scale = 1.4826 * merged["mad"].where(merged["mad"] >= min_mad)
    merged["robust_z"] = (merged[count_col] - merged["median"]) / scale
    return merged[
        [window_col, zone_col, count_col, "hour_of_week", "median", "mad", "robust_z"]
    ]


def ewma_residual_scores(
    demand: pd.DataFrame,
    *,
    halflife: float = 24.0,
    span_std: int = 24 * 7,
    min_std: float = 1.0,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Compute residual scores against an exponentially weighted baseline.

    For each zone:
    baseline_t = EWM(y_{<t})
    score_t = (y_t - baseline_t) / rolling_std(residual_{<t})
    """
    panel = prepare_hourly_panel(demand, ts_col=window_col, zone_col=zone_col, count_col=count_col)
    out = panel.copy()
    out["baseline"] = np.nan
    out["residual"] = np.nan
    out["ewma_z"] = np.nan

    for zone, idx in out.groupby(zone_col).groups.items():
        g = out.loc[idx].sort_values(window_col).copy()
        y = g[count_col].astype(float)
        baseline = y.shift(1).ewm(halflife=halflife, adjust=False).mean()
        residual = y - baseline
        resid_std = residual.shift(1).rolling(span_std, min_periods=8).std(ddof=0)
        resid_std = resid_std.where(resid_std >= min_std)
        score = residual / resid_std
        out.loc[g.index, "baseline"] = baseline.to_numpy()
        out.loc[g.index, "residual"] = residual.to_numpy()
        out.loc[g.index, "ewma_z"] = score.to_numpy()

    return out[[window_col, zone_col, count_col, "baseline", "residual", "ewma_z"]]


def detect_consensus_anomalies(
    demand: pd.DataFrame,
    *,
    robust_threshold: float = 3.5,
    ewma_threshold: float = 3.0,
    min_votes: int = 2,
    window_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Flag anomalies supported by multiple detectors.

    Returns one row per zone-hour with detector booleans, vote count, and a
    combined severity score.
    """
    robust_base = fit_robust_baseline(
        demand, window_col=window_col, zone_col=zone_col, count_col=count_col
    )
    robust = robust_z_scores(
        demand,
        robust_base,
        window_col=window_col,
        zone_col=zone_col,
        count_col=count_col,
    )[[window_col, zone_col, count_col, "robust_z"]]
    ewma = ewma_residual_scores(
        demand,
        window_col=window_col,
        zone_col=zone_col,
        count_col=count_col,
    )[[window_col, zone_col, count_col, "ewma_z"]]

    merged = robust.merge(ewma, on=[window_col, zone_col, count_col], how="outer")
    merged["robust_flag"] = merged["robust_z"].abs() >= robust_threshold
    merged["ewma_flag"] = merged["ewma_z"].abs() >= ewma_threshold
    merged["votes"] = merged[["robust_flag", "ewma_flag"]].fillna(False).sum(axis=1)
    merged["severity"] = merged[["robust_z", "ewma_z"]].abs().max(axis=1)

    flagged = merged.loc[merged["votes"] >= min_votes].copy()
    flagged = flagged.sort_values(["severity", window_col], ascending=[False, True]).reset_index(drop=True)
    logger.info("consensus anomalies: %d rows with >= %d votes", len(flagged), min_votes)
    return flagged
