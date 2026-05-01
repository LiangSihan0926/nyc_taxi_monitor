"""Benchmarking / profiling helpers.

Designed for repeatable experiments in the final project report. These helpers
measure runtime and peak Python memory with ``tracemalloc`` so different methods
can be compared under a consistent interface.
"""
from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass
from typing import Any, Callable, Dict

import pandas as pd

from .advanced_anomaly import detect_consensus_anomalies, ewma_residual_scores, fit_robust_baseline, robust_z_scores
from .anomaly import detect_anomalies, fit_baseline
from .forecast import backtest_zone_forecasts
from .utils import get_logger

__all__ = [
    "BenchResult",
    "benchmark_callable",
    "benchmark_many",
    "benchmark_anomaly_methods",
    "benchmark_forecast_methods",
    "benchmark_forecast_and_anomaly",
]

logger = get_logger(__name__)


@dataclass(frozen=True)
class BenchResult:
    name: str
    seconds: float
    peak_bytes: int
    extra: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "seconds": self.seconds,
            "peak_bytes": self.peak_bytes,
            **self.extra,
        }


def benchmark_callable(
    name: str,
    fn: Callable[..., Any],
    /,
    *args,
    repeats: int = 3,
    warmup: int = 1,
    **kwargs,
) -> BenchResult:
    """Benchmark a callable with warmup and repeated timed runs."""
    for _ in range(max(warmup, 0)):
        fn(*args, **kwargs)

    best = float("inf")
    best_peak = 0
    last_out = None
    for _ in range(max(repeats, 1)):
        tracemalloc.start()
        t0 = time.perf_counter()
        last_out = fn(*args, **kwargs)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if elapsed < best:
            best = elapsed
            best_peak = peak

    extra = {}
    if hasattr(last_out, "__len__"):
        try:
            extra["rows"] = len(last_out)
        except Exception:  # pragma: no cover
            pass
    return BenchResult(name=name, seconds=best, peak_bytes=best_peak, extra=extra)


def benchmark_many(cases: Dict[str, Callable[[], Any]], *, repeats: int = 3) -> pd.DataFrame:
    rows = []
    for name, fn in cases.items():
        res = benchmark_callable(name, fn, repeats=repeats)
        rows.append(res.as_dict())
    return pd.DataFrame(rows).sort_values("seconds").reset_index(drop=True)


def benchmark_anomaly_methods(demand: pd.DataFrame) -> pd.DataFrame:
    """Compare original z-score anomaly detection with stronger variants."""
    baseline = fit_baseline(demand)
    robust_baseline = fit_robust_baseline(demand)
    cases = {
        "zscore_detect": lambda: detect_anomalies(demand, baseline),
        "robust_zscore": lambda: robust_z_scores(demand, robust_baseline),
        "ewma_residual": lambda: ewma_residual_scores(demand),
        "consensus": lambda: detect_consensus_anomalies(demand),
    }
    out = benchmark_many(cases)
    logger.info("benchmarked %d anomaly methods", len(out))
    return out


def benchmark_forecast_methods(demand: pd.DataFrame) -> pd.DataFrame:
    """Benchmark built-in forecasting baselines using a common backtest."""
    methods = [
        "seasonal_naive_24",
        "seasonal_naive_168",
        "moving_average_24",
        "moving_average_168",
        "ewm_12",
        "ewm_24",
    ]
    rows = []
    for method in methods:
        res = benchmark_callable(
            method,
            backtest_zone_forecasts,
            demand,
            methods=[method],
            repeats=1,
        )
        rows.append(res.as_dict())
    return pd.DataFrame(rows).sort_values("seconds").reset_index(drop=True)

def benchmark_forecast_and_anomaly(demand: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Run both anomaly and forecast benchmarks and combine results."""
    logger.info("Starting combined benchmark suite...")
    
    # We add **kwargs here to catch extra arguments like 'time_col' 
    # and safely ignore them since the sub-functions don't need them.
    
    anomaly_df = benchmark_anomaly_methods(demand)
    forecast_df = benchmark_forecast_methods(demand)
    
    combined = pd.concat([anomaly_df, forecast_df], ignore_index=True)
    return combined
