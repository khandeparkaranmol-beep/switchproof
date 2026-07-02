"""Wilson score interval — honest error bars for a proportion.

Why Wilson, not p ± 1.96·SE: the naive interval breaks at the edges (it can leave [0,1]
and gives a zero-width band at 100%). Wilson behaves correctly at 100%/0% and small n —
exactly where switch-agreement numbers live. Returns (low, high) in [0,1].
"""

from __future__ import annotations

import math
from typing import Tuple


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
