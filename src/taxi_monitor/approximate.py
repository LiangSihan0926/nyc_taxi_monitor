"""Extension 2: Approximate counting for very large streams.

Two classic algorithms from the course, both implemented without extra deps:

* :class:`ReservoirSampler` — uniform random sample of size *k* from a stream
  of unknown length (Vitter, 1985).  We can then estimate zone counts as
  ``sample_count[zone] * (N / k)``.
* :class:`CountMinSketch` — sublinear-memory frequency estimator with a
  provable error bound of ``eps * N`` at probability ``1 - delta`` (Cormode
  & Muthukrishnan, 2005).  No false-negatives; overestimates only.

Both expose a matching :py:meth:`top_k` for direct comparison with the exact
``dict`` baseline.
"""
from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Hashable, Iterable, List, Tuple

import numpy as np

from .hotspot import HotspotResult, top_k_from_counts
from .utils import DEFAULT_SEED, get_logger

__all__ = ["ReservoirSampler", "CountMinSketch", "compare_topk"]

logger = get_logger(__name__)


# --- Reservoir sampling ---------------------------------------------------


@dataclass
class ReservoirSampler:
    """Algorithm R from Vitter (1985).

    After observing ``n`` items, the reservoir contains a uniform random
    sample of size ``min(k, n)``.
    """

    k: int
    seed: int = DEFAULT_SEED
    _reservoir: List[Hashable] = field(default_factory=list)
    _n: int = 0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self):
        if self.k <= 0:
            raise ValueError("k must be positive")
        self._rng = random.Random(self.seed)

    @property
    def n(self) -> int:
        return self._n

    def add(self, item: Hashable) -> None:
        self._n += 1
        if len(self._reservoir) < self.k:
            self._reservoir.append(item)
            return
        # Replace an item with probability k/n.
        j = self._rng.randint(0, self._n - 1)
        if j < self.k:
            self._reservoir[j] = item

    def add_many(self, items: Iterable[Hashable]) -> None:
        for it in items:
            self.add(it)

    def sample(self) -> List[Hashable]:
        return list(self._reservoir)

    def estimated_counts(self) -> Dict[Hashable, float]:
        """Extrapolate sample frequencies back to full-stream estimates."""
        if not self._reservoir:
            return {}
        sample_size = len(self._reservoir)
        scale = self._n / sample_size
        return {item: cnt * scale for item, cnt in Counter(self._reservoir).items()}

    def top_k(self, k: int) -> List[HotspotResult]:
        """Approximate top-k from the reservoir (rounded to ints)."""
        est = {int(z): int(round(c)) for z, c in self.estimated_counts().items()}
        return top_k_from_counts(est, k)


# --- Count-Min Sketch -----------------------------------------------------


def _hash_pair(item: Hashable, seed: int) -> int:
    """Deterministic 64-bit-ish hash of `item` under `seed`.

    We avoid Python's built-in :func:`hash` because ``PYTHONHASHSEED`` randomness
    can make cross-process results non-reproducible.
    """
    payload = f"{seed}:{item}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False)


@dataclass
class CountMinSketch:
    """Count-Min Sketch with configurable width and depth.

    Parameters
    ----------
    width : int
        Number of counters per row.  Controls the additive error bound
        (``error ~ N / width``).
    depth : int
        Number of hash functions / rows.  Controls the failure probability
        (``delta ~ (1/2)**depth``).
    seed : int
        Base seed for the `depth` hash functions.
    """

    width: int = 2048
    depth: int = 5
    seed: int = DEFAULT_SEED
    _table: np.ndarray = field(init=False, repr=False)
    _seeds: Tuple[int, ...] = field(init=False, repr=False)
    _n: int = 0

    def __post_init__(self):
        if self.width <= 0 or self.depth <= 0:
            raise ValueError("width and depth must be positive")
        self._table = np.zeros((self.depth, self.width), dtype=np.int64)
        rng = random.Random(self.seed)
        self._seeds = tuple(rng.randrange(1, 2**31 - 1) for _ in range(self.depth))

    # --- classmethods ----------------------------------------------------

    @classmethod
    def from_bounds(
        cls, eps: float, delta: float, seed: int = DEFAULT_SEED
    ) -> "CountMinSketch":
        """Construct a sketch achieving additive error ``eps * N`` with
        probability ``1 - delta``.

        Uses ``width = ceil(e / eps)`` and ``depth = ceil(ln(1/delta))``.
        """
        if not (0 < eps < 1):
            raise ValueError("eps must be in (0, 1)")
        if not (0 < delta < 1):
            raise ValueError("delta must be in (0, 1)")
        width = max(1, math.ceil(math.e / eps))
        depth = max(1, math.ceil(math.log(1 / delta)))
        return cls(width=width, depth=depth, seed=seed)

    # --- core ops --------------------------------------------------------

    def _indices(self, item: Hashable) -> List[int]:
        return [_hash_pair(item, s) % self.width for s in self._seeds]

    def add(self, item: Hashable, count: int = 1) -> None:
        self._n += count
        for row, col in enumerate(self._indices(item)):
            self._table[row, col] += count

    def add_many(self, items: Iterable[Hashable]) -> None:
        for it in items:
            self.add(it, 1)

    def estimate(self, item: Hashable) -> int:
        cols = self._indices(item)
        return int(min(self._table[row, col] for row, col in enumerate(cols)))

    @property
    def n(self) -> int:
        return self._n

    def memory_bytes(self) -> int:
        """Rough memory footprint — just the counter array."""
        return int(self._table.nbytes)

    def top_k(self, items: Iterable[Hashable], k: int) -> List[HotspotResult]:
        """Estimate frequencies for every item in `items` and return top-k.

        The sketch itself does **not** store keys, so callers must supply the
        candidate zone-id set.  In practice that's the 263 NYC zones — tiny.
        """
        estimates = {int(it): self.estimate(it) for it in items}
        return top_k_from_counts(estimates, k)


# --- helpers --------------------------------------------------------------


def compare_topk(
    exact: List[HotspotResult], approx: List[HotspotResult]
) -> Dict[str, float]:
    """Summarize overlap / rank-agreement between two top-k lists."""
    ex_ids = [r.zone_id for r in exact]
    ap_ids = [r.zone_id for r in approx]
    overlap = set(ex_ids) & set(ap_ids)
    k = min(len(ex_ids), len(ap_ids))
    if k == 0:
        return {"overlap": 0, "jaccard": 0.0, "rank_correlation": 0.0}
    jaccard = len(overlap) / len(set(ex_ids) | set(ap_ids))

    # Spearman's ρ on the common items (manual to avoid a scipy dependency).
    if overlap:
        ex_rank = {z: i for i, z in enumerate(ex_ids)}
        ap_rank = {z: i for i, z in enumerate(ap_ids)}
        diffs = [ex_rank[z] - ap_rank[z] for z in overlap]
        n = len(overlap)
        if n == 1:
            rho = 1.0
        else:
            rho = 1 - (6 * sum(d * d for d in diffs)) / (n * (n * n - 1))
    else:
        rho = 0.0

    return {
        "overlap": len(overlap),
        "jaccard": float(jaccard),
        "rank_correlation": float(rho),
    }
