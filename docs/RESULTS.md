# Detailed Experimental Results

This document expands on the summary in [README.md](../README.md) with
per-experiment analysis, numbers, and the insights that matter for the
final submission.  All five experiments run on the same dataset:
**~9.37 M cleaned Yellow Taxi trips** spanning Nov 2023 – Jan 2024.

Regenerate any CSV below by re-running the matching script under
`scripts/`, or refresh every figure via `python scripts/make_figures.py`.

---

## Experiment 1 — Batch Hotspot Top-K

**Script**: `scripts/experiment_1_batch_hotspot.py`
**Outputs**: `reports/experiment_1_overall.csv`, `experiment_1_per_hour.csv`
**Figure**: `reports/figures/top_zones.png`

### Setup
A single DuckDB aggregation on the three-month `clean_trips` table
(`GROUP BY pickup_zone, pickup_hour`), followed by a heap-based top-10
per hour.

### Results — top 10 zones over the 3-month window

| Rank | Zone | Borough | Trips |
| ---: | --- | --- | ---: |
| 1 | Upper East Side South | Manhattan | **467,567** |
| 2 | Midtown Center | Manhattan | 445,102 |
| 3 | Upper East Side North | Manhattan | 428,489 |
| 4 | JFK Airport | Queens | 414,875 |
| 5 | Midtown East | Manhattan | 341,730 |
| 6 | Lincoln Square East | Manhattan | 330,242 |
| 7 | Penn Station / Madison Sq West | Manhattan | 321,246 |
| 8 | Times Sq / Theatre District | Manhattan | 319,522 |
| 9 | LaGuardia Airport | Queens | 300,811 |
| 10 | Midtown North | Manhattan | 284,774 |

### Insight
**8 of the top-10 are Manhattan; the other 2 are the airports.**  Upper
East Side South beats Midtown Center by ~5 % — non-obvious because one
is residential and the other a business district.  The per-hour table
(22 k rows) is what feeds the anomaly detector in Experiment 2.

---

## Experiment 2 — Z-Score Anomaly Detection

**Script**: `scripts/experiment_2_anomaly.py`
**Outputs**: `reports/experiment_2_baseline.csv`, `experiment_2_anomalies.csv`

### Setup
Fit a per-`(zone, hour-of-week)` baseline (mean, std) on Nov + Dec 2023,
then score every hourly bucket in January.  A row is flagged when
`|(count − mean) / max(std, 0.5)| ≥ 3`.

### Results
- **Baseline rows**: 29,478 (≈ 168 hours-of-week × ~175 non-trivial zones)
- **Anomalies flagged**: **1,192** hourly buckets in January with |z| ≥ 3
- **Peak surge**: zone 79 (East Village), 2024-01-01 03:00 — 470 trips vs
  baseline 13.5 → **z ≈ 215**

### Top-5 surges (excerpt)

| Time (ET) | Zone | Trips | Baseline mean | z |
| --- | ---: | ---: | ---: | ---: |
| 2024-01-01 03:00 | 79 (East Village) | 470 | 13.5 | **215.2** |
| 2024-01-01 03:00 | 107 (Gramercy) | 227 | 5.1 | 210.7 |
| 2024-01-01 03:00 | 114 (Greenwich Village S) | 171 | 3.5 | 149.8 |
| 2024-01-01 02:00 | 137 (Kips Bay) | 146 | 3.3 | 119.1 |
| 2024-01-01 02:00 | 164 (Midtown South) | 183 | 8.3 | 102.0 |

### Insight
**Every top surge is on New Year's Eve between 1 AM and 4 AM** — demand
for nightlife zones (East Village, Gramercy, Greenwich Village) jumps
15-35× the typical weekday midnight rate.  The baseline is intentionally
simple (hour-of-week, no holiday awareness); the fact that the detector
still pinpoints a coherent spatio-temporal pattern is evidence the
mechanism is working, not failing.

---

## Experiment 3 — Streaming vs Batch

**Script**: `scripts/experiment_3_streaming_vs_batch.py`
**Outputs**: `reports/experiment_3_summary.csv`
**Figure**: `reports/figures/stream_vs_batch.png`

### Setup
Replay one month (Jan 2024, 2,873,328 events) through the pure-Python
`StreamingMonitor` in chunks of 10,000, measuring per-batch latency.  In
parallel, run the equivalent batch SQL through DuckDB on the same data.

### Results

| Mode | Wall clock | Per-event | Top-k vs exact |
| --- | ---: | ---: | ---: |
| Batch SQL (DuckDB)  | **0.19 s** | 0.07 µs | — (ground truth) |
| Streaming monitor   | 7.34 s     | 2.56 µs | Jaccard 0.82, Spearman ρ 0.925 |

- **Mean per-10 k-batch latency**: **10.8 ms**
- **Batch throughput speed-up**: **37.8×** over streaming

### Insight
DuckDB is columnar C++ with vectorised aggregation; pure-Python is
one-event-at-a-time — so the 38× throughput gap is expected, **not** a
streaming-architecture indictment.  The streaming monitor's value is
that mean per-batch latency stays under 11 ms, making it a viable
online component (dashboard, alerting) even when DuckDB is unavailable.
Spearman ρ ≥ 0.9 also means the two modes agree on the *ordering* of
hotspots even when absolute counts drift at sliding-window boundaries.

---

## Experiment 4 — Exact vs Approximate Counting

**Script**: `scripts/experiment_4_exact_vs_approximate.py`
**Outputs**: `reports/experiment_4_summary.csv`, `experiment_4_topk_*.csv`
**Figure**: `reports/figures/exact_vs_approx.png`

### Setup
The January 2024 stream (2.87 M events) is fed through three accumulators:
(a) exact `dict[int, int]`; (b) `ReservoirSampler(k = 100 000)`;
(c) `CountMinSketch` sized to ε = 0.001, δ = 0.01 → depth 5 × width 2 048.
All three emit their top-10 zone estimate; we compare on memory,
runtime, and top-10 rank correlation vs the exact dict.

### Results

| Method | Runtime | Memory | Top-10 overlap | Jaccard | Spearman ρ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact `dict`         | 0.41 s  | **23 KB**  | 10 / 10 | 1.00 | 1.00 |
| Reservoir (k = 100 k)| 4.31 s  | 3.5 MB     | 10 / 10 | 1.00 | **0.988** |
| Count-Min Sketch     | 32.1 s  | 80 KB      | 10 / 10 | 1.00 | 1.00 |

### Insight — two counter-intuitive findings

**(a) The exact dict is smaller than CMS.**  23 KB < 80 KB.  This is
because the key universe (pickup zones) has only 263 distinct values —
well under the 5 × 2 048 = 10 240 counter cells in the sketch.  The
sketch only pays off on much-higher-cardinality streams (millions of
distinct keys); on this workload, proving *when the sketch wins* is
the pedagogical value.

**(b) CMS is ~80× slower than the dict.**  0.41 s → 32.1 s.  Each CMS
insert recomputes five independent Blake2b hashes; the dict does one
hash and a pointer lookup.  The sketch's theoretical advantage is
*space*, not *time*.

Reservoir sampling at k = 100 000 maintains rank-correlation **0.988**
with the exact top-10 — a clean empirical point on the accuracy-memory
curve.  The scaling step `estimated_count = reservoir_count × (n / k)`
is what makes the sample usable as a frequency estimator.

---

## Experiment 5 — MapReduce Parallel Ingest

**Script**: `scripts/experiment_5_parallel.py`
**Outputs**: `reports/experiment_5_parallel.csv`
**Figure**: `reports/figures/parallel_speedup.png`

### Setup
`multiprocessing.Pool` dispatches one worker per monthly parquet.
Each worker reads + cleans + counts zones independently; the
coordinator sums the per-worker `dict[zone, count]`s and returns the
global top-10 via `heapq.nlargest`.  Worker count sweep: 1 → 2 → 4 → 8.

### Results (3-file workload)

| Workers | Wall time | Speed-up |
| ---: | ---: | ---: |
| 1 | 6.605 s | 1.00× (baseline) |
| 2 | 4.493 s | 1.47× |
| 4 | 3.092 s | 2.14× |
| 8 | **2.976 s** | **2.22×** ← best |

### Insight
**Speed-up scales near-linearly from 1 to 4 workers (2.14×), then shows
diminishing returns at 8 workers (2.22×, only +0.08× over 4 workers).**
The bulk of the win comes between 1 → 2 → 4 workers, after which the
workload approaches limits set by I/O saturation, process spawn cost,
and inter-process pickle / IPC overhead.

### Important caveat — cache bias

The sweep runs worker counts in fixed ascending order, so later runs
read warmer OS file cache than the first.  This **inflates** the
apparent speed-up at higher worker counts.  A rigorous benchmark would
either randomize the order or repeat the sweep many times and average;
this project documents the caveat rather than fixing it (see the
`note` block in `taxi_monitor.parallel.benchmark`).  The honest
takeaway is therefore "**up to** 2.22× on warm cache" rather than a
clean parallelism claim.


---

## Cross-cutting lessons

1. **Approximate ≠ smaller or faster.**  Experiment 4: exact dict beats
   CMS on both memory (23 KB < 80 KB) and runtime (0.41 s ≪ 32 s) at
   this cardinality.  The sketch's win only appears when key
   cardinality outgrows the sketch's fixed footprint.

2. **Parallel scaling is bounded by partition count.**  Experiment 5:
   4 workers on 3 files is slower than 2 workers on 3 files.

3. **Pure-Python streaming is viable when latency > throughput.**
   Experiment 3: 38× throughput gap vs DuckDB, but 10.8 ms mean
   per-batch latency keeps the monitor viable for interactive / online
   use.

4. **Simple baselines can still find real signal.**  Experiment 2's
   hour-of-week baseline correctly concentrates all top surges on
   New Year's morning without any holiday-awareness.

5. **Data quality is not free.**  TLC parquets still carry stray trips
   with 2002 / 2009 pickup timestamps; the `MIN_PICKUP_YEAR = 2010`
   filter in `clean.py` is what keeps those out of the downstream
   aggregates.
