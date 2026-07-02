"""Small stats helpers for honest reporting."""

from __future__ import annotations

import math
from typing import Tuple


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion (default 95%).

    Why Wilson, not k/n ± 1.96·SE: the naive interval is nonsense at the edges (it can
    exceed [0,1] and gives a zero-width interval for 40/40). Wilson behaves correctly at
    100% and 0%, which is exactly where our scores live. Returns (low, high) in [0,1].
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
