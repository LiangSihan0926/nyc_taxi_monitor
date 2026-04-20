"""Tests for taxi_monitor.approximate."""
from __future__ import annotations

import random
from collections import Counter

import pytest

from taxi_monitor.approximate import CountMinSketch, ReservoirSampler, compare_topk
from taxi_monitor.hotspot import HotspotResult, top_k_from_counts


def _make_zipf_stream(n: int, num_zones: int = 263, seed: int = 7):
    rng = random.Random(seed)
    # Simple heavy-tail: zone i is drawn with probability ~1/(i+1)
    weights = [1 / (i + 1) for i in range(num_zones)]
    total = sum(weights)
    weights = [w / total for w in weights]
    cum = [sum(weights[: i + 1]) for i in range(num_zones)]
    zones = []
    for _ in range(n):
        r = rng.random()
        for i, c in enumerate(cum):
            if r <= c:
                zones.append(i + 1)
                break
    return zones


# --- Reservoir -------------------------------------------------------------


def test_reservoir_small_stream_keeps_everything():
    r = ReservoirSampler(k=100)
    r.add_many([1, 2, 3])
    assert sorted(r.sample()) == [1, 2, 3]
    assert r.n == 3


def test_reservoir_overflow_keeps_k():
    r = ReservoirSampler(k=50)
    r.add_many(range(10_000))
    assert len(r.sample()) == 50
    assert r.n == 10_000


def test_reservoir_top_k_matches_roughly():
    stream = _make_zipf_stream(5_000)
    exact_top = top_k_from_counts(Counter(stream), 5)

    r = ReservoirSampler(k=2_000)
    r.add_many(stream)
    approx_top = r.top_k(5)

    cmp = compare_topk(exact_top, approx_top)
    # With 40%-size reservoir on a heavy-tail, the top-5 overlap is high.
    assert cmp["overlap"] >= 4


def test_reservoir_rejects_nonpositive_k():
    with pytest.raises(ValueError):
        ReservoirSampler(k=0)


def test_reservoir_is_reproducible():
    a = ReservoirSampler(k=20, seed=1)
    a.add_many(range(5_000))
    b = ReservoirSampler(k=20, seed=1)
    b.add_many(range(5_000))
    assert a.sample() == b.sample()


# --- Count-Min Sketch ------------------------------------------------------


def test_count_min_upper_bounds_true_counts():
    stream = _make_zipf_stream(2_000)
    truth = Counter(stream)

    cms = CountMinSketch(width=1024, depth=5)
    cms.add_many(stream)

    # Every estimate must be >= true count (CMS never under-counts).
    for zone, count in truth.items():
        est = cms.estimate(zone)
        assert est >= count


def test_count_min_top_k_is_close_to_exact():
    stream = _make_zipf_stream(10_000)
    exact_top = top_k_from_counts(Counter(stream), 10)

    cms = CountMinSketch(width=2048, depth=5)
    cms.add_many(stream)
    approx_top = cms.top_k(sorted(set(stream)), 10)

    cmp = compare_topk(exact_top, approx_top)
    # With a 2048-wide sketch the heavy hitters should all show up.
    assert cmp["overlap"] >= 9


def test_count_min_from_bounds_rejects_bad_args():
    with pytest.raises(ValueError):
        CountMinSketch.from_bounds(eps=1.1, delta=0.1)
    with pytest.raises(ValueError):
        CountMinSketch.from_bounds(eps=0.1, delta=0.0)


def test_count_min_from_bounds_sizes_make_sense():
    cms = CountMinSketch.from_bounds(eps=0.01, delta=0.01)
    # width ≈ e/eps ≈ 272; depth ≈ ln(1/0.01) ≈ 5
    assert cms.width >= 100
    assert cms.depth >= 4


def test_count_min_rejects_bad_shape():
    with pytest.raises(ValueError):
        CountMinSketch(width=0, depth=1)


def test_count_min_memory_bytes_positive():
    cms = CountMinSketch(width=128, depth=3)
    assert cms.memory_bytes() > 0


# --- compare_topk ----------------------------------------------------------


def test_compare_topk_identical():
    a = [HotspotResult(i + 1, i + 1, 10 - i) for i in range(3)]
    cmp = compare_topk(a, a)
    assert cmp["overlap"] == 3
    assert cmp["jaccard"] == 1.0
    assert cmp["rank_correlation"] == pytest.approx(1.0)


def test_compare_topk_empty():
    cmp = compare_topk([], [])
    assert cmp["overlap"] == 0
    assert cmp["jaccard"] == 0.0


def test_compare_topk_single_overlap_is_rho_one():
    a = [HotspotResult(1, 10, 5)]
    b = [HotspotResult(1, 10, 7)]
    cmp = compare_topk(a, b)
    assert cmp["rank_correlation"] == 1.0


def test_compare_topk_no_overlap():
    a = [HotspotResult(1, 1, 5), HotspotResult(2, 2, 4)]
    b = [HotspotResult(1, 99, 5), HotspotResult(2, 100, 4)]
    cmp = compare_topk(a, b)
    assert cmp["overlap"] == 0
    assert cmp["rank_correlation"] == 0.0
