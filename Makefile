.PHONY: setup data pipeline experiments figures test clean all help

VENV := .venv
PY   := $(VENV)/bin/python

help:
	@echo "Available targets:"
	@echo "  setup        Create venv and install package with dev+viz extras"
	@echo "  data         Download NYC TLC parquet files (Nov'23 – Jan'24)"
	@echo "  pipeline     Run ingest -> clean -> DuckDB load"
	@echo "  experiments  Run all five experiments (outputs under reports/)"
	@echo "  figures      Regenerate reports/figures/*.png from reports/*.csv"
	@echo "  test         Run pytest with coverage (fail-under 80)"
	@echo "  all          setup -> data -> pipeline -> experiments -> figures -> test"
	@echo "  clean        Remove venv, caches, and build artifacts"

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev,viz]"

data:
	$(PY) scripts/download_data.py

pipeline:
	$(PY) scripts/run_pipeline.py --months 2023-11 2023-12 2024-01

experiments:
	$(PY) scripts/experiment_1_batch_hotspot.py
	$(PY) scripts/experiment_2_anomaly.py
	$(PY) scripts/experiment_3_streaming_vs_batch.py
	$(PY) scripts/experiment_4_exact_vs_approximate.py
	$(PY) scripts/experiment_5_parallel.py

figures:
	$(PY) scripts/make_figures.py

test:
	$(PY) -m pytest --cov=taxi_monitor --cov-report=term-missing

all: setup data pipeline experiments figures test

clean:
	rm -rf $(VENV) .pytest_cache .coverage coverage.xml build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
