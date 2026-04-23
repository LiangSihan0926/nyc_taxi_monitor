"""taxi_monitor — Scalable NYC Taxi Demand Monitoring System.

Public entry points are re-exported for convenience:

    from taxi_monitor import (
        ingest, clean, database, aggregate,
        hotspot, anomaly, streaming, approximate, utils,
    )
"""
from importlib import metadata as _metadata

try:  # pragma: no cover - trivial
    __version__ = _metadata.version("taxi_monitor")
except _metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"

from . import (  # noqa: F401  (re-export)
    aggregate,
    analytics,
    anomaly,
    advanced_anomaly,
    approximate,
    benchmarking,
    clean,
    dashboard,
    database,
    forecast,
    hotspot,
    ingest,
    parallel,
    streaming,
    utils,
)

__all__ = [
    "aggregate",
    "analytics",
    "anomaly",
    "advanced_anomaly",
    "approximate",
    "benchmarking",
    "clean",
    "dashboard",
    "database",
    "forecast",
    "hotspot",
    "ingest",
    "parallel",
    "streaming",
    "utils",
    "__version__",
]
