"""Forecasting utilities built on top of zone-hour demand aggregates.

This module is intentionally lightweight: it uses only pandas / numpy so it
fits the project's current dependency set. The goal is not to beat modern
forecasting libraries, but to add a reproducible forecasting layer on top of the
existing monitoring pipeline.

Typical workflow
----------------
1. Build hourly demand with ``aggregate.zone_hour_demand(conn)``.
2. Call :func:`backtest_zone_forecasts` to compare simple forecasting baselines.
3. Optionally call :func:`forecast_next_horizon` to produce next-horizon
   predictions for each zone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .utils import get_logger

__all__ = [
    "ForecastResult",
    "prepare_hourly_panel",
    "seasonal_naive_forecast",
    "moving_average_forecast",
    "ewm_forecast",
    "backtest_zone_forecasts",
    "forecast_next_horizon",
]

logger = get_logger(__name__)


@dataclass(frozen=True)
class ForecastResult:
    method: str
    mae: float
    rmse: float
    mape: float
    coverage: float
    n_forecasts: int


def prepare_hourly_panel(
    demand: pd.DataFrame,
    *,
    ts_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
    full_grid: bool = True,
    freq: str = "H",
) -> pd.DataFrame:
    """Return a dense hourly panel with columns [pickup_hour, zone_id, trips].

    The existing aggregate output is sparse: a zone-hour pair is absent when its
    trip count is zero. Forecasting models usually need an explicit zero-filled
    panel, so this helper expands the grid when ``full_grid=True``.
    """
    required = {ts_col, zone_col, count_col}
    missing = required - set(demand.columns)
    if missing:
        raise ValueError(f"demand DataFrame missing columns: {missing}")

    df = demand[[ts_col, zone_col, count_col]].copy()
    df[ts_col] = pd.to_datetime(df[ts_col])
    df[zone_col] = df[zone_col].astype(int)
    df[count_col] = df[count_col].astype(float)

    if not full_grid or df.empty:
        return df.sort_values([zone_col, ts_col]).reset_index(drop=True)

    all_ts = pd.date_range(df[ts_col].min(), df[ts_col].max(), freq=freq)
    all_zones = np.sort(df[zone_col].unique())
    grid = pd.MultiIndex.from_product([all_ts, all_zones], names=[ts_col, zone_col])
    dense = (
        df.set_index([ts_col, zone_col])
        .reindex(grid, fill_value=0)
        .reset_index()
        .sort_values([zone_col, ts_col])
        .reset_index(drop=True)
    )
    dense[count_col] = dense[count_col].astype(int)
    return dense


def seasonal_naive_forecast(
    panel: pd.DataFrame,
    *,
    seasonal_lag: int = 24,
    zone_col: str = "zone_id",
    ts_col: str = "pickup_hour",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Forecast each point by copying the value from ``seasonal_lag`` periods ago."""
    df = panel.sort_values([zone_col, ts_col]).copy()
    df["yhat"] = df.groupby(zone_col)[count_col].shift(seasonal_lag)
    df["method"] = f"seasonal_naive_lag_{seasonal_lag}"
    return df


def moving_average_forecast(
    panel: pd.DataFrame,
    *,
    window: int = 24,
    min_periods: int = 1,
    zone_col: str = "zone_id",
    ts_col: str = "pickup_hour",
    count_col: str = "trips",
) -> pd.DataFrame:
    """One-step-ahead rolling-mean forecast per zone."""
    df = panel.sort_values([zone_col, ts_col]).copy()
    hist = df.groupby(zone_col)[count_col].shift(1)
    df["yhat"] = (
        hist.groupby(df[zone_col])
        .rolling(window=window, min_periods=min_periods)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["method"] = f"moving_average_{window}"
    return df


def ewm_forecast(
    panel: pd.DataFrame,
    *,
    halflife: float = 12.0,
    zone_col: str = "zone_id",
    ts_col: str = "pickup_hour",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Exponentially weighted one-step-ahead forecast per zone."""
    df = panel.sort_values([zone_col, ts_col]).copy()

    def _ewm_shifted(s: pd.Series) -> pd.Series:
        return s.shift(1).ewm(halflife=halflife, adjust=False).mean()

    df["yhat"] = df.groupby(zone_col)[count_col].transform(_ewm_shifted)
    df["method"] = f"ewm_halflife_{halflife:g}"
    return df


def _forecast_metrics(actual: pd.Series, pred: pd.Series) -> Dict[str, float]:
    mask = actual.notna() & pred.notna()
    if mask.sum() == 0:
        return {"mae": np.nan, "rmse": np.nan, "mape": np.nan, "coverage": 0.0, "n": 0}

    a = actual.loc[mask].astype(float)
    p = pred.loc[mask].astype(float)
    err = a - p
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(np.square(err))))
    denom = a.replace(0, np.nan)
    mape = float(np.nanmean(np.abs(err) / denom) * 100.0)
    coverage = float(mask.mean())
    return {"mae": mae, "rmse": rmse, "mape": mape, "coverage": coverage, "n": int(mask.sum())}


_METHODS = {
    "seasonal_naive_24": lambda df: seasonal_naive_forecast(df, seasonal_lag=24),
    "seasonal_naive_168": lambda df: seasonal_naive_forecast(df, seasonal_lag=168),
    "moving_average_24": lambda df: moving_average_forecast(df, window=24),
    "moving_average_168": lambda df: moving_average_forecast(df, window=168),
    "ewm_12": lambda df: ewm_forecast(df, halflife=12),
    "ewm_24": lambda df: ewm_forecast(df, halflife=24),
}


def backtest_zone_forecasts(
    demand: pd.DataFrame,
    *,
    methods: Optional[Sequence[str]] = None,
    holdout_hours: int = 24 * 7,
    ts_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Backtest simple forecasting baselines on the final ``holdout_hours``.

    Returns a summary DataFrame sorted by RMSE.
    """
    panel = prepare_hourly_panel(demand, ts_col=ts_col, zone_col=zone_col, count_col=count_col)
    all_hours = np.sort(panel[ts_col].unique())
    if len(all_hours) <= holdout_hours:
        raise ValueError("not enough history for requested holdout_hours")

    cutoff = all_hours[-holdout_hours]
    selected = methods or tuple(_METHODS)
    rows: List[Dict[str, float]] = []

    for name in selected:
        if name not in _METHODS:
            raise KeyError(f"unknown forecasting method: {name}")
        scored = _METHODS[name](panel)
        test = scored.loc[scored[ts_col] >= cutoff].copy()
        metrics = _forecast_metrics(test[count_col], test["yhat"])
        rows.append(
            {
                "method": name,
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "mape": metrics["mape"],
                "coverage": metrics["coverage"],
                "n_forecasts": metrics["n"],
                "holdout_hours": int(holdout_hours),
            }
        )

    out = pd.DataFrame(rows).sort_values(["rmse", "mae"], na_position="last").reset_index(drop=True)
    logger.info("forecast backtest complete: %d methods on %d rows", len(out), len(panel))
    return out


def forecast_next_horizon(
    demand: pd.DataFrame,
    *,
    method: str = "seasonal_naive_24",
    horizon: int = 24,
    ts_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
) -> pd.DataFrame:
    """Produce next-``horizon`` forecasts for each zone.

    We recursively roll the chosen baseline forward. For simple baselines this is
    deterministic and dependency-free.
    """
    if method not in _METHODS:
        raise KeyError(f"unknown forecasting method: {method}")

    panel = prepare_hourly_panel(demand, ts_col=ts_col, zone_col=zone_col, count_col=count_col)
    last_ts = pd.Timestamp(panel[ts_col].max())
    future_ts = pd.date_range(last_ts + pd.Timedelta(hours=1), periods=horizon, freq="H")
    zones = np.sort(panel[zone_col].unique())

    hist = {
        int(zone): panel.loc[panel[zone_col] == zone, count_col].astype(float).tolist()
        for zone in zones
    }
    rows: List[Dict[str, object]] = []

    for step, ts in enumerate(future_ts, start=1):
        for zone in zones:
            series = hist[int(zone)]
            if method == "seasonal_naive_24":
                yhat = series[-24] if len(series) >= 24 else series[-1]
            elif method == "seasonal_naive_168":
                yhat = series[-168] if len(series) >= 168 else series[-1]
            elif method == "moving_average_24":
                yhat = float(np.mean(series[-24:]))
            elif method == "moving_average_168":
                yhat = float(np.mean(series[-168:]))
            elif method == "ewm_12":
                yhat = float(pd.Series(series).ewm(halflife=12, adjust=False).mean().iloc[-1])
            elif method == "ewm_24":
                yhat = float(pd.Series(series).ewm(halflife=24, adjust=False).mean().iloc[-1])
            else:  # pragma: no cover - guarded above
                raise KeyError(method)

            series.append(float(yhat))
            rows.append({ts_col: ts, zone_col: int(zone), "yhat": max(float(yhat), 0.0), "method": method})

    return pd.DataFrame(rows, columns=[ts_col, zone_col, "yhat", "method"])
