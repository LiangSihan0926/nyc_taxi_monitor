"""Utility helpers: logging, paths, reproducible seeding."""
from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Optional

import numpy as np

__all__ = [
    "DEFAULT_SEED",
    "PROJECT_ROOT",
    "DATA_DIR",
    "RAW_DIR",
    "CLEAN_DIR",
    "DB_PATH",
    "get_logger",
    "set_seed",
    "ensure_dir",
]

DEFAULT_SEED = 42

# Resolve paths relative to the repo so scripts work no matter where they are
# invoked from.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
CLEAN_DIR: Path = DATA_DIR / "clean"
DB_PATH: Path = DATA_DIR / "taxi_monitor.duckdb"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger (idempotent — safe to call repeatedly)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    # Prevent duplicate logs if the root logger is also configured.
    logger.propagate = False
    return logger


def set_seed(seed: Optional[int] = None) -> int:
    """Seed Python's `random`, NumPy, and `PYTHONHASHSEED` for reproducibility.

    Returns the seed actually used so callers can log / record it.
    """
    if seed is None:
        seed = DEFAULT_SEED
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    return seed


def ensure_dir(path: os.PathLike) -> Path:
    """Create `path` (and parents) if it does not already exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
