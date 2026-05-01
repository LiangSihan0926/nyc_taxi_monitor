# nyc_taxi_monitor

**Scalable NYC Taxi Demand Monitoring System**  

A reproducible big-data pipeline for monitoring NYC taxi demand at scale. Built on
[NYC TLC Trip Records][tlc], the system processes **9.37M cleaned Yellow Taxi trips**
from **November 2023 to January 2024** and compares four processing approaches:

- DuckDB-based batch SQL analytics
- Python-based online streaming monitoring
- Approximate counting with Count-Min Sketch and reservoir sampling
- Local MapReduce-style parallel aggregation using Python multiprocessing

The project evaluates trade-offs in **runtime, memory usage, accuracy, latency, and
parallel speed-up** for hotspot detection, anomaly monitoring, demand forecasting,
and business-oriented mobility analytics.

[tlc]: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

![CI](https://github.com/LiangSihan0926/nyc_taxi_monitor/actions/workflows/ci.yml/badge.svg) ![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen) ![Tests](https://img.shields.io/badge/tests-78%20passing-brightgreen) ![License](https://img.shields.io/badge/license-MIT-green)

> **Pitch** — A reproducible NYC taxi demand-monitoring system that uses one real 9.37M-trip workload to compare the practical trade-offs between batch SQL, streaming, approximate counting, and local MapReduce-style aggregation.

---

## Main Findings

The project shows that no single processing method dominates across all settings:
DuckDB is fastest for offline aggregation, streaming is useful for low-latency
online monitoring, approximate counting only helps under the right cardinality
regime, and parallel speed-up is bounded by input partitioning.

Across **9,369,680 cleaned Yellow Taxi trips**, the system finds:

- **DuckDB batch processing is ~38× faster than the Python streaming monitor**
  on throughput: 0.19 s vs 7.34 s end-to-end on 2.87M events. However, the
  streaming monitor keeps mean per-batch latency at **10.8 ms**, making it a
  viable option for online monitoring.
- **Count-Min Sketch recovers the exact top-10 pickup zones** with Jaccard
  similarity **1.00** and Spearman rank correlation **1.00** using 80 KB.
  However, the exact dictionary is smaller in this setting, using only 23 KB,
  because there are only 263 taxi zones.
- **Reservoir sampling with k = 100,000 reaches rank correlation 0.988**
  against the exact top-10, showing a clear accuracy-memory trade-off.
- **Local MapReduce-style ingest achieves its best speed-up at 2 workers**
  with a **1.30×** improvement over the sequential baseline. Performance
  regresses at 4 and 8 workers because the workload has only 3 input partitions.
- **Z-score anomaly detection flags 1,192 demand surges** against a weekly
  hour-of-week baseline, concentrated around Manhattan airports, Midtown, and
  the Upper East Side.
- **Weekly seasonality dominates taxi demand**: the seasonal naive baseline
  with a 168-hour lag achieves the best MAE, substantially outperforming moving
  average and EWMA baselines.
- **Consensus anomaly detection improves robustness** by combining robust
  z-score and EWMA residual scoring, producing 381 high-confidence anomalies.
- **Demand patterns are highly structured across time and space**, with clear
  weekday/weekend differences, concentrated OD flows, and distinct airport vs
  Manhattan trip regimes.

| Experiment | Metric | Value |
| --- | --- | ---: |
| Top zones (3 mo)           | Busiest pickup zone       | Upper East Side South — **467,567** trips |
| Streaming vs batch         | Batch speed-up            | **37.8×** (0.19 s vs 7.34 s) |
| Streaming latency          | Mean per 10 k batch       | **10.8 ms** |
| Exact vs approximate       | CMS top-10 Jaccard        | **1.00** (80 KB) |
| Exact vs approximate       | Reservoir rank-corr       | **0.988** (3.5 MB, k = 100 k) |
| MapReduce ingest           | Best speed-up (2 workers) | **1.30×** vs sequential |
| Anomalies                  | Surges flagged (&#124;z&#124; > 3) | **1,192** |
| Forecasting                | Best MAE (seasonal naive) | **~2.9** |
| Advanced anomaly           | Consensus anomalies       | **381 (≥ 2 votes)** |

### Why it matters

The most important results are counter-intuitive:

1. **Approximate counting is not always more memory-efficient.**  
   With only 263 taxi zones, the exact dictionary uses less memory than the
   Count-Min Sketch. The sketch becomes more attractive only when the key
   cardinality is large enough to justify its fixed counter-array cost.

2. **Parallel speed-up is bounded by partition count, not CPU count.**  
   Adding more workers does not help when there are only three input parquet
   files. This mirrors real Hadoop / Spark tuning trade-offs: parallelism is
   limited by the number and size of input partitions.

3. **Simple forecasting baselines can be strong when structure is clear.**  
   The seasonal naive model beats moving average and EWMA baselines because NYC
   taxi demand has strong weekly periodicity.

<table>
  <tr>
    <td align="center" width="50%">
      <img src="reports/figures/top_zones.png"/>
      <br/><em>Top-10 pickup zones (Nov 23 – Jan 24) — 8 / 10 are Manhattan, the other two are JFK and LaGuardia.</em>
    </td>
    <td align="center" width="50%">
      <img src="reports/figures/exact_vs_approx.png"/>
      <br/><em>Exact dict vs reservoir sample vs Count-Min Sketch — CMS recovers top-10 perfectly, but an exact dict is actually smaller here (low cardinality).</em>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="reports/figures/stream_vs_batch.png"/>
      <br/><em>DuckDB batch vs pure-Python streaming on 2.87 M events — 38× throughput gap, but streaming holds 10.8 ms mean batch latency.</em>
    </td>
    <td align="center" width="50%">
      <img src="reports/figures/parallel_speedup.png"/>
      <br/><em>MapReduce wall time vs workers — speed-up plateaus at 2 workers because there are only 3 input partitions.</em>
    </td>
  </tr>
  <tr>
  <td align="center" width="50%">
    <img src="reports/figures/forecast_mae.png"/>
    <br/><em>Forecast MAE — weekly seasonal naive significantly outperforms other baselines, confirming strong weekly structure.</em>
  </td>
  <td align="center" width="50%">
    <img src="reports/figures/anomaly_severity.png"/>
    <br/><em>Top anomaly severity — detected events are rare but extreme, consistent with real demand shocks.</em>
  </td>
</tr>
</table>

---

## Architecture

![Architecture diagram — ingest & clean feed DuckDB (batch) and a streaming monitor with approximate counters; multiprocessing.Pool branches into a parallel map-reduce](docs/architecture.png)

*Figure 1 — Four data paths share the same cleaner: DuckDB batch SQL, a
pure-Python streaming monitor, sublinear approximate counters
(reservoir + Count-Min Sketch), and a MapReduce-style parallel ingest.*

Each layer maps to a module under `src/taxi_monitor/`:

| Module                | Role                                                         |
| --------------------- | ------------------------------------------------------------ |
| `ingest.py`           | Download + parquet/CSV loaders                               |
| `clean.py`            | Drop dirty rows, derive `pickup_hour` / `trip_duration`      |
| `database.py`         | DuckDB schema + upserts                                      |
| `aggregate.py`        | SQL aggregations (`zone × hour`, busiest zones, …)           |
| `hotspot.py`          | `O(n log k)` top-k via a bounded min-heap                    |
| `anomaly.py`          | Per-(zone, hour-of-week) z-score surge detection             |
| `advanced_anomaly.py` | Robust z-score, EWMA residual scoring, consensus anomalies   |
| `forecast.py`         | Lightweight forecasting baselines + next-horizon prediction  |
| `analytics.py`        | Business-oriented SQL analytics and operational summaries    |
| `benchmarking.py`     | Runtime / memory benchmarking helpers for experiments        |
| `dashboard.py`        | Reproducible matplotlib dashboard generation                 |
| `streaming.py`        | Online `StreamingMonitor` with optional sliding window       |
| `approximate.py`      | `ReservoirSampler` + `CountMinSketch`                        |
| `parallel.py`         | `multiprocessing.Pool` map-reduce over parquet files         |
| `utils.py`            | Logging, seeding, path helpers                               |

---

## Quick start

All experiment outputs and figures are already committed under `reports/`, so the
main results can be inspected without rerunning the full pipeline.

For a quick verification, run:

```bash
# Clone + enter the repo
git clone https://github.com/LiangSihan0926/nyc_taxi_monitor.git
cd nyc_taxi_monitor

# Set up the environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,viz]"

# Run the test suite
python -m pytest
```
---
## Full Reproduction

To re-derive all results from the raw NYC TLC data, use the Makefile workflow:

```bash
# 1. Install dependencies
make setup

# 2. Download ~150 MB of TLC data
make data

# 3. Rebuild the DuckDB store
make pipeline

# 4. Re-run all experiments
make experiments

# 5. Regenerate figures
make figures

# 6. Run tests
make test
```
---
## Testing, CI, and Reproducibility Guarantees

The project is designed to be easy to verify without rerunning the full data
pipeline.

- **Automated tests:** The test suite covers data ingestion, cleaning, DuckDB
  aggregation, hotspot detection, anomaly detection, streaming, approximate
  counting, local MapReduce-style aggregation, forecasting, dashboard generation,
  benchmarking, and utility functions.
- **Coverage gate:** `pytest-cov` is configured with an 80% fail-under threshold
  in `pyproject.toml`; current branch coverage is approximately 97%.
- **Deterministic behavior:** Random seeds are controlled through
  `taxi_monitor.utils.set_seed`, and tests re-seed automatically through a
  pytest fixture.
- **No network dependency in tests:** Network downloads are monkey-patched in
  tests, so the test suite does not depend on live NYC TLC servers.
- **Dirty-data fixtures:** Unit tests use small synthetic parquet fixtures with
  intentional data issues, including negative distances, invalid zones, and
  duplicates, to verify the cleaning logic.
- **Committed outputs:** Experiment CSVs and generated figures are committed
  under `reports/`, allowing graders to inspect results without rerunning the
  full pipeline.
- **CI:** GitHub Actions runs the test suite across Python 3.9–3.12.

To run the same verification locally:

```bash
make test
# or
python -m pytest --cov=taxi_monitor --cov-report=term-missing
```
---

## Optional: Running with Docker 

To ensure complete reproducibility across any operating system without configuring local Python environments, this project is fully containerized. The Docker image packages the code, dependencies, and pre-computed reports.

```bash
# 1. Build the image
make docker-build

# 2. Run the interactive dashboard
make docker-run
```
---

## Optional: Run Individual Experiments

Each experiment can also be run directly:

```bash
python scripts/experiment_1_batch_hotspot.py
python scripts/experiment_2_anomaly.py
python scripts/experiment_3_streaming_vs_batch.py
python scripts/experiment_4_exact_vs_approximate.py
python scripts/experiment_5_parallel.py
python scripts/experiment_6_forecast.py
python scripts/experiment_7_advanced_anomaly.py
python scripts/experiment_8_business_analytics.py
```

---

## Experiments and Outputs

Each experiment writes its results to a predictable location.

| # | Experiment | Script | What it measures | Output CSVs / Artifacts |
| - | ---------- | ------ | ---------------- | ----------------------- |
| 1 | Batch hotspot | `scripts/experiment_1_batch_hotspot.py` | Top-k busiest zones per hour using batch SQL | `reports/experiment_1_{overall,per_hour}.csv` |
| 2 | Anomaly detection | `scripts/experiment_2_anomaly.py` | Demand surges vs Nov/Dec baseline using z-scores | `reports/experiment_2_{baseline,anomalies}.csv` |
| 3 | Stream vs batch | `scripts/experiment_3_streaming_vs_batch.py` | Correctness and latency of streaming vs batch processing | `reports/experiment_3_summary.csv` |
| 4 | Exact vs approximate | `scripts/experiment_4_exact_vs_approximate.py` | Memory, runtime, and top-k accuracy of exact counting, reservoir sampling, and CMS | `reports/experiment_4_{summary,topk_*}.csv` |
| 5 | Parallel MapReduce | `scripts/experiment_5_parallel.py` | Wall time and speed-up of local MapReduce-style parallel ingest | `reports/experiment_5_parallel.csv` |
| 6 | Forecasting | `scripts/experiment_6_forecast.py` | Forecast backtesting and next-horizon demand prediction | `reports/experiment_6_forecast.csv` |
| 7 | Advanced anomaly | `scripts/experiment_7_advanced_anomaly.py` | Robust z-score, EWMA residual scoring, and consensus anomaly detection | `reports/experiment_7_advanced_anomaly.csv` |
| 8 | Business analytics | `scripts/experiment_8_business_analytics.py` | Weekday/weekend demand, OD flows, and airport vs Manhattan patterns | `reports/{weekday_weekend_demand,top_od_pairs,airport_vs_manhattan}.csv` |
| — | Benchmark | `scripts/run_benchmark.py` | Runtime and memory benchmarking helpers | `reports/benchmark_results.csv` |
| — | Dashboard | `scripts/run_dashboard.py` | Reproducible dashboard generation | `reports/dashboard.png` |

`scripts/make_figures.py` reads the experiment summary CSVs and writes
`reports/figures/{top_zones,exact_vs_approx,stream_vs_batch,parallel_speedup}.png`.

### What "MapReduce-style" means in Experiment 5

Experiment 5 intentionally mirrors the MapReduce pattern from the course:

- **Map step** — each worker process (spawned by `multiprocessing.Pool`) takes
  one input *partition* (a single monthly parquet), loads + cleans it, and
  emits a local `{zone_id: trip_count}` dictionary.  Workers share nothing;
  each has its own Python interpreter, bypassing the GIL.
- **Reduce step** — the coordinator receives every worker's partial dict and
  folds them with `heapq.nlargest` on the merged `Counter`, returning the
  global top-k.  This is a *commutative, associative aggregation*, which is
  exactly what MapReduce requires for correctness.

Speed-up is **sub-linear** beyond 2 workers on this workload because the job
only has **3 input partitions** (Nov / Dec / Jan parquets).  Adding more
workers than partitions means the extra processes sit idle while still paying
fixed pool **spawn** and inter-process **pickle / IPC overhead**.  This is the
same reason Hadoop / Spark tune block size against cluster size —
parallelism is bounded by the number of partitions, not by the number of CPU
cores.

---

## Repository layout

```text
nyc_taxi_monitor/
├── README.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── app.py
├── Dockerfile  
├── .dockerignore 
├── docs/
│   ├── architecture.mmd       # Mermaid source for the system diagram
│   ├── architecture.png       # Rendered diagram used in README
│   └── RESULTS.md             # Per-experiment deep-dive analysis
├── src/taxi_monitor/
│   ├── __init__.py
│   ├── ingest.py
│   ├── clean.py
│   ├── database.py
│   ├── aggregate.py
│   ├── hotspot.py
│   ├── anomaly.py
│   ├── advanced_anomaly.py
│   ├── forecast.py
│   ├── analytics.py
│   ├── benchmarking.py
│   ├── dashboard.py
│   ├── streaming.py
│   ├── approximate.py
│   ├── parallel.py
│   └── utils.py
├── scripts/
│   ├── __init__.py
│   ├── download_data.py
│   ├── run_pipeline.py
│   ├── experiment_1_batch_hotspot.py
│   ├── experiment_2_anomaly.py
│   ├── experiment_3_streaming_vs_batch.py
│   ├── experiment_4_exact_vs_approximate.py
│   ├── experiment_5_parallel.py
│   ├── experiment_6_forecast.py
│   ├── experiment_7_advanced_anomaly.py
│   ├── experiment_8_business_analytics.py
│   ├── run_benchmark.py
│   ├── run_dashboard.py
│   └── make_figures.py
├── tests/
│   ├── conftest.py
│   ├── test_utils.py
│   ├── test_ingest.py
│   ├── test_clean.py
│   ├── test_database_aggregate.py
│   ├── test_hotspot.py
│   ├── test_anomaly.py
│   ├── test_streaming.py
│   ├── test_approximate.py
│   ├── test_parallel.py
│   └── test_extensions_smoke.py
├── .github/workflows/ci.yml  # pytest matrix on Python 3.9 – 3.12
├── Makefile                  # make setup | data | pipeline | experiments | figures | test
├── data/          # git-ignored; populated by download_data.py
└── reports/       # experiment CSV outputs + figures/*.png
```
---

## Limitations

- The workload contains only three monthly parquet partitions, so parallel
  speed-up is bounded by the small number of input files.
- The taxi zone cardinality is low, which limits the memory advantage of
  approximate counting methods.
- The streaming monitor is simulated from historical data rather than connected
  to a live event source.
- Forecasting baselines are intentionally lightweight and are used mainly to
  demonstrate seasonal structure rather than maximize predictive performance.
- The analysis focuses on three months of Yellow Taxi data; longer multi-year
  data would provide a stronger test of seasonality, anomaly stability, and
  scaling behavior.
  
---

## Future Work

- Increase partition granularity to better evaluate parallel scaling.
- Add a real streaming source such as Kafka or Pub/Sub.
- Extend anomaly detection with event calendars, weather, and holidays.
- Compare DuckDB with Spark for larger multi-year workloads.
- Add interactive filtering to the Streamlit dashboard.
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
* **Parallel map-reduce.**  `multiprocessing.Pool` dispatches each
  monthly parquet to a separate process (bypassing the GIL); per-worker
  `{zone: count}` dicts are then merged by a single `heapq.nlargest`
  reduce step.  Tie-break on ascending `zone_id` matches `hotspot.py` so
  top-k results are identical to the batch pipeline.  The observed
  speed-up plateaus at the number of input partitions — classic
  MapReduce scaling behaviour on a small partition count.

---

## Documentation & Additional Materials

Beyond this README, three supporting documents live under `docs/`:

| File                      | Purpose                                                                             |
| ------------------------- | ----------------------------------------------------------------------------------- |
| `docs/architecture.png`   | Rendered system architecture (shown in *Architecture* above).                       |
| `docs/architecture.mmd`   | Mermaid source for the architecture diagram — edit and re-export via https://mermaid.live. |
| `docs/RESULTS.md`         | Per-experiment deep-dive: setup, full tables, and insights for the core experiments. |


---

## License

MIT — see `LICENSE`.
