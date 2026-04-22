"""Generate the plots embedded in README.md from ``reports/*.csv``.

Re-running the experiments updates the CSVs; re-running this script
updates the PNGs in ``reports/figures/``.  Missing CSVs (e.g. you
haven't run ``experiment_5_parallel.py`` yet) are skipped with a log
line rather than erroring.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — safe for CI and for `python scripts/...`
import matplotlib.pyplot as plt
import pandas as pd

from taxi_monitor.utils import PROJECT_ROOT, ensure_dir, get_logger

logger = get_logger("make_figures")

REPORTS_DIR = PROJECT_ROOT / "reports"
FIG_DIR = ensure_dir(REPORTS_DIR / "figures")


def _save(fig: plt.Figure, name: str) -> None:
    path = FIG_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    logger.info("wrote %s", path)


def fig_top_zones() -> None:
    src = REPORTS_DIR / "experiment_1_overall.csv"
    if not src.exists():
        logger.warning("skip top_zones — %s missing", src)
        return
    df = pd.read_csv(src)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(df["zone_name"][::-1], df["trips"][::-1], color="#1f77b4")
    ax.set_xlabel("trips")
    ax.set_title("Top-10 pickup zones (Nov 2023 – Jan 2024)")
    _save(fig, "top_zones.png")


def fig_exact_vs_approx() -> None:
    src = REPORTS_DIR / "experiment_4_summary.csv"
    if not src.exists():
        logger.warning("skip exact_vs_approx — %s missing", src)
        return
    df = pd.read_csv(src)
    colors = ["#555555", "#1f77b4", "#ff7f0e"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.bar(df["method"], df["runtime_sec"], color=colors)
    ax1.set_title("Runtime (s)")
    ax1.tick_params(axis="x", rotation=20)
    ax2.bar(df["method"], df["memory_kb"], color=colors)
    ax2.set_yscale("log")
    ax2.set_title("Memory (KB, log scale)")
    ax2.tick_params(axis="x", rotation=20)
    _save(fig, "exact_vs_approx.png")


def fig_stream_vs_batch() -> None:
    src = REPORTS_DIR / "experiment_3_summary.csv"
    if not src.exists():
        logger.warning("skip stream_vs_batch — %s missing", src)
        return
    df = pd.read_csv(src)
    kv = dict(zip(df["metric"], df["value"]))
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        ["batch (DuckDB)", "streaming"],
        [kv["batch_total_sec"], kv["stream_total_sec"]],
        color=["#2ca02c", "#d62728"],
    )
    ax.set_ylabel("seconds")
    ax.set_title(f"Streaming vs batch on {int(kv['events']):,} trips")
    _save(fig, "stream_vs_batch.png")


def fig_parallel_speedup() -> None:
    src = REPORTS_DIR / "experiment_5_parallel.csv"
    if not src.exists():
        logger.warning("skip parallel_speedup — %s missing", src)
        return
    df = pd.read_csv(src)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.plot(df["workers"], df["wall_sec"], "o-", color="#1f77b4")
    ax1.set_xlabel("worker processes")
    ax1.set_ylabel("wall time (s)")
    ax1.set_title("MapReduce ingest — wall time")
    ax2.plot(df["workers"], df["speedup"], "o-", color="#ff7f0e")
    ax2.set_xlabel("worker processes")
    ax2.set_ylabel("speedup vs 1 worker")
    ax2.set_title("MapReduce ingest — speedup")
    _save(fig, "parallel_speedup.png")


def main() -> None:
    fig_top_zones()
    fig_exact_vs_approx()
    fig_stream_vs_batch()
    fig_parallel_speedup()
    logger.info("done — figures in %s", FIG_DIR)


if __name__ == "__main__":
    main()
