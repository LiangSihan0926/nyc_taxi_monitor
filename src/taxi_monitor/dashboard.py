"""Matplotlib-based visualization / dashboard helpers.

The project already produces tables and experiment outputs. This module turns
those outputs into a single reproducible dashboard image without adding a new
heavy dependency like Streamlit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .hotspot import top_k_per_window
from .utils import ensure_dir, get_logger

__all__ = [
    "plot_citywide_demand",
    "plot_top_zones",
    "plot_anomaly_timeline",
    "plot_forecast_vs_actual",
    "build_dashboard",
]

logger = get_logger(__name__)


def plot_citywide_demand(
    demand: pd.DataFrame,
    *,
    ts_col: str = "pickup_hour",
    count_col: str = "trips",
    ax=None,
):
    ax = ax or plt.gca()
    city = demand.groupby(ts_col, as_index=False)[count_col].sum().sort_values(ts_col)
    ax.plot(pd.to_datetime(city[ts_col]), city[count_col])
    ax.set_title("City-wide hourly demand")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Trips")
    return ax


def plot_top_zones(
    demand: pd.DataFrame,
    *,
    k: int = 10,
    zone_col: str = "zone_id",
    count_col: str = "trips",
    ax=None,
):
    ax = ax or plt.gca()
    top = (
        demand.groupby(zone_col, as_index=False)[count_col]
        .sum()
        .sort_values(count_col, ascending=False)
        .head(k)
    )
    ax.bar(top[zone_col].astype(str), top[count_col])
    ax.set_title(f"Top {k} zones by total trips")
    ax.set_xlabel("Zone")
    ax.set_ylabel("Trips")
    return ax


def plot_anomaly_timeline(
    anomalies: pd.DataFrame,
    *,
    ts_col: str = "pickup_hour",
    ax=None,
):
    ax = ax or plt.gca()
    if anomalies.empty:
        ax.set_title("Anomaly timeline (no anomalies)")
        return ax
    counts = anomalies.groupby(ts_col).size().reset_index(name="n_anomalies")
    ax.plot(pd.to_datetime(counts[ts_col]), counts["n_anomalies"])
    ax.set_title("Anomalies over time")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Flagged zone-hours")
    return ax


def plot_forecast_vs_actual(
    actual: pd.DataFrame,
    forecast: pd.DataFrame,
    *,
    zone_id: Optional[int] = None,
    ts_col: str = "pickup_hour",
    zone_col: str = "zone_id",
    count_col: str = "trips",
    ax=None,
):
    ax = ax or plt.gca()
    a = actual.copy()
    f = forecast.copy()
    if zone_id is None:
        zone_id = int(a.groupby(zone_col)[count_col].sum().sort_values(ascending=False).index[0])
    a = a.loc[a[zone_col] == zone_id, [ts_col, count_col]].rename(columns={count_col: "actual"})
    f = f.loc[f[zone_col] == zone_id, [ts_col, "yhat"]]
    merged = a.merge(f, on=ts_col, how="outer").sort_values(ts_col)
    ax.plot(pd.to_datetime(merged[ts_col]), merged["actual"], label="actual")
    ax.plot(pd.to_datetime(merged[ts_col]), merged["yhat"], label="forecast")
    ax.set_title(f"Forecast vs actual — zone {zone_id}")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Trips")
    ax.legend()
    return ax


def build_dashboard(
    demand: pd.DataFrame,
    *,
    anomalies: Optional[pd.DataFrame] = None,
    forecast: Optional[pd.DataFrame] = None,
    output_path: Optional[str | Path] = None,
    figsize=(14, 10),
) -> plt.Figure:
    """Build a 2x2 dashboard and optionally save it."""
    fig, axes = plt.subplots(2, 2, figsize=figsize)
    plot_citywide_demand(demand, ax=axes[0, 0])
    plot_top_zones(demand, ax=axes[0, 1])
    plot_anomaly_timeline(anomalies if anomalies is not None else pd.DataFrame(columns=["pickup_hour"]), ax=axes[1, 0])

    if forecast is not None and not forecast.empty:
        plot_forecast_vs_actual(demand, forecast, ax=axes[1, 1])
    else:
        hotspot = top_k_per_window(demand, k=5)
        if hotspot.empty:
            axes[1, 1].set_title("Top-5 hotspots over time")
        else:
            pivot = hotspot.pivot(index="pickup_hour", columns="rank", values="zone_id").ffill()
            for col in pivot.columns[:3]:
                axes[1, 1].plot(pd.to_datetime(pivot.index), pivot[col], label=f"rank {col}")
            axes[1, 1].set_title("Hotspot ranks over time")
            axes[1, 1].set_xlabel("Hour")
            axes[1, 1].set_ylabel("Zone ID")
            axes[1, 1].legend()

    fig.tight_layout()
    if output_path is not None:
        out = ensure_dir(Path(output_path).parent) / Path(output_path).name
        fig.savefig(out, bbox_inches="tight", dpi=150)
        logger.info("saved dashboard to %s", out)
    return fig
