"""Tests for taxi_monitor.utils — small module, so we hit every function."""
from __future__ import annotations

import logging
import os
import random
from pathlib import Path

import numpy as np

from taxi_monitor.utils import (
    DEFAULT_SEED,
    PROJECT_ROOT,
    ensure_dir,
    get_logger,
    set_seed,
)


def test_get_logger_is_idempotent():
    a = get_logger("t_utils.demo")
    b = get_logger("t_utils.demo")
    assert a is b
    # Handlers should not accumulate on repeated calls.
    assert len(a.handlers) == 1
    assert a.level == logging.INFO
    assert a.propagate is False


def test_set_seed_makes_rng_deterministic():
    set_seed(123)
    py_a = random.random()
    np_a = np.random.rand(3).tolist()

    set_seed(123)
    py_b = random.random()
    np_b = np.random.rand(3).tolist()

    assert py_a == py_b
    assert np_a == np_b
    assert os.environ["PYTHONHASHSEED"] == "123"


def test_set_seed_defaults():
    used = set_seed()
    assert used == DEFAULT_SEED


def test_ensure_dir_creates(tmp_path: Path):
    target = tmp_path / "nested" / "deeper"
    assert not target.exists()
    out = ensure_dir(target)
    assert out.exists()
    assert out.is_dir()
    # Second call is a no-op, not an error.
    ensure_dir(target)


def test_project_root_is_repo_root():
    # utils.py lives at src/taxi_monitor/utils.py; parents[2] is the repo root.
    assert (PROJECT_ROOT / "pyproject.toml").exists()
