# nyc_taxi_monitor

**Scalable NYC Taxi Demand Monitoring System** — a final project for ORIE 5270
(Big Data Analysis).  Built around the [NYC TLC Trip Records][tlc] it
combines a SQL batch pipeline, an online streaming monitor, and two
approximate-counting algorithms so we can compare their time / memory /
accuracy trade-offs on real data.

[tlc]: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

---

## Architecture

```
         ┌──────────────┐    ┌──────────────┐    ┌────────────────┐
 raw →   │   ingest +   │ →  │   DuckDB /   │ →  │  batch hotspot │
parquet  │   clean      │    │   SQL agg.   │    │  + anomaly     │
         └──────────────┘    └──────────────┘    └────────────────┘
                 │
                 ▼
         ┌──────────────┐          ┌──────────────────────────────┐
         │  streaming   │   ↔↔↔↔   │  approximate counters:       │
         │  monitor     │          │   reservoir + count-min      │
         └──────────────┘          └──────────────────────────────┘
           Batch pipeline  →  Streaming extension  →  Approximation layer
```

Each layer maps to a module under `src/taxi_monitor/`:

| Module           | Role                                                    |
| ---------------- | ------------------------------------------------------- |
| `ingest.py`      | Download + parquet/CSV loaders                          |
| `clean.py`       | Drop dirty rows, derive `pickup_hour` / `trip_duration` |
| `database.py`    | DuckDB schema + upserts                                 |
| `aggregate.py`   | SQL aggregations (`zone × hour`, busiest zones, …)      |
| `hotspot.py`     | `O(n log k)` top-k via a bounded min-heap               |
| `anomaly.py`     | Per-(zone, hour-of-week) z-score surge detection        |
| `streaming.py`   | Online `StreamingMonitor` with optional sliding window  |
| `approximate.py` | `ReservoirSampler` + `CountMinSketch`                   |
| `utils.py`       | Logging, seeding, path helpers                          |

---

## Quick start

```bash
# 1. Clone + enter the repo
git clone https://github.com/LiangSihan0926/nyc_taxi_monitor.git
cd nyc_taxi_monitor

# 2. Create a venv and install in editable mode
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Download ~150 MB of NYC TLC data (Nov'23, Dec'23, Jan'24 + zone lookup)
python scripts/download_data.py

# 4. Run the batch pipeline (loads clean trips into DuckDB)
python scripts/run_pipeline.py --months 2023-11 2023-12 2024-01

# 5. Run the four experiments
python scripts/experiment_1_batch_hotspot.py
python scripts/experiment_2_anomaly.py
python scripts/experiment_3_streaming_vs_batch.py
python scripts/experiment_4_exact_vs_approximate.py
```

Experiment outputs land in `reports/*.csv`.

---

## Experiments

| # | Script                                     | What it measures                                  |
| - | ------------------------------------------ | ------------------------------------------------- |
| 1 | `experiment_1_batch_hotspot.py`            | Top-k busiest zones per hour (batch SQL)          |
| 2 | `experiment_2_anomaly.py`                  | Demand surges vs Nov/Dec baseline (z-score)       |
| 3 | `experiment_3_streaming_vs_batch.py`       | Correctness + latency of streaming vs batch       |
| 4 | `experiment_4_exact_vs_approximate.py`     | Memory / runtime / top-k accuracy of exact vs reservoir vs CMS |

---

## Testing & reproducibility

* `pytest` + `pytest-cov`; fail-under coverage gate set to **80 %** in
  `pyproject.toml` (currently **~98 %** branch coverage).
* All RNGs are seeded via `taxi_monitor.utils.set_seed`; tests use a
  `@pytest.fixture(autouse=True)` that re-seeds per test.
* No test hits the network — `ingest.download_file` is monkey-patched.
* Unit-test fixtures synthesize a tiny parquet file with *intentional* dirty
  rows (negative distance, bad zones, duplicates, …) so the cleaning code is
  exercised on known bad input.

Run tests:

```bash
python -m pytest --cov=taxi_monitor --cov-report=term-missing
```

---

## Repository layout

```text
nyc_taxi_monitor/
├── README.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── src/taxi_monitor/
│   ├── __init__.py
│   ├── ingest.py
│   ├── clean.py
│   ├── database.py
│   ├── aggregate.py
│   ├── hotspot.py
│   ├── anomaly.py
│   ├── streaming.py
│   ├── approximate.py
│   └── utils.py
├── scripts/
│   ├── download_data.py
│   ├── run_pipeline.py
│   ├── experiment_1_batch_hotspot.py
│   ├── experiment_2_anomaly.py
│   ├── experiment_3_streaming_vs_batch.py
│   └── experiment_4_exact_vs_approximate.py
├── tests/
│   ├── conftest.py
│   ├── test_utils.py
│   ├── test_ingest.py
│   ├── test_clean.py
│   ├── test_database_aggregate.py
│   ├── test_hotspot.py
│   ├── test_anomaly.py
│   ├── test_streaming.py
│   └── test_approximate.py
├── data/          # git-ignored; populated by download_data.py
└── reports/       # experiment CSV outputs
```

---

## Algorithmic notes

* **Hotspot top-k.**  `heapq` min-heap of size `k`; O(n log k) time, O(k)
  space.  Deterministic tie-breaking on `zone_id`.
* **Anomaly detection.**  Baseline is the per-`(zone, hour-of-week)` mean and
  population std of hourly trip counts.  Using `hour_of_week ∈ [0, 168)`
  captures weekly seasonality (weekday rush vs weekend) cheaply without a
  full time-series model.  A `min_std` guard prevents huge spurious z-scores
  on near-empty zones.
* **Reservoir sampling.**  Vitter's Algorithm R: after observing `n` items,
  the reservoir holds a uniform random sample of size `min(k, n)`.  We
  scale sample frequencies back to full-stream estimates via `n / k`.
* **Count-Min Sketch.**  `depth × width` counter array with `depth`
  independent Blake2b hashes (we avoid `hash()` because `PYTHONHASHSEED`
  randomness would break reproducibility across runs).  `from_bounds(eps,
  delta)` sizes the sketch to achieve additive error `eps·N` with
  probability `1 − delta`.  CMS never under-counts; it only over-counts.

---

## License

MIT — see `LICENSE`.
