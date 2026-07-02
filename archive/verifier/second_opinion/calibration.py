"""Calibration — turning a raw confidence into an honest one.

The whole promise of the product is that "90% confident" means right 90% of the time.
A raw model confidence does not satisfy that — models are systematically overconfident.
So we FIT a monotonic mapping from raw confidence -> empirical accuracy on labelled data
(isotonic regression via Pool Adjacent Violators), and apply it at runtime.

Design choices:
- Isotonic (monotonic) fit: more confidence should never map to less accuracy, but we make
  no shape assumption beyond that. No sklearn dependency — PAV is ~15 lines of pure Python.
- Honest fallback: with no fitted map (or before fitting), we shrink toward 0.5 rather than
  trust raw confidence. Under-claiming certainty beats bluffing.
- Fit and evaluation must use DIFFERENT splits (fit on dev, report ECE on test) — otherwise
  the calibration number is a lie about itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

_CALIB_PATH = Path(__file__).resolve().parent.parent / "benchmark" / "calibration.json"


# --------------------------------------------------------------------------- #
# Metric
# --------------------------------------------------------------------------- #

def ece(pairs: List[Tuple[float, bool]], bins: int = 10) -> float:
    """Expected Calibration Error over (confidence, correct) pairs."""
    if not pairs:
        return 0.0
    buckets: dict = {}
    for conf, correct in pairs:
        idx = min(bins - 1, int(max(0.0, min(1.0, conf)) * bins))
        buckets.setdefault(idx, []).append((conf, 1.0 if correct else 0.0))
    total = len(pairs)
    out = 0.0
    for items in buckets.values():
        avg_conf = sum(c for c, _ in items) / len(items)
        acc = sum(ok for _, ok in items) / len(items)
        out += (len(items) / total) * abs(avg_conf - acc)
    return out


# --------------------------------------------------------------------------- #
# Isotonic regression (Pool Adjacent Violators)
# --------------------------------------------------------------------------- #

def _pav(points: List[List[float]]) -> List[Tuple[float, float]]:
    """points: [[x, y, weight], ...] sorted by x. Returns monotonic non-decreasing (x, y)."""
    blocks: List[List[float]] = []  # each: [sum(x*w), pooled_y, weight]
    for x, y, w in points:
        blocks.append([x * w, y, w])
        while len(blocks) >= 2 and blocks[-2][1] > blocks[-1][1]:
            sxw2, y2, w2 = blocks.pop()
            sxw1, y1, w1 = blocks.pop()
            nw = w1 + w2
            blocks.append([sxw1 + sxw2, (y1 * w1 + y2 * w2) / nw, nw])
    return [(sxw / w, y) for sxw, y, w in blocks]


# --------------------------------------------------------------------------- #
# Calibrator
# --------------------------------------------------------------------------- #

class Calibrator:
    def __init__(self, anchors: List[Tuple[float, float]], n: int) -> None:
        # anchors: monotonic (raw_confidence, calibrated_confidence), sorted by x.
        self.anchors = anchors
        self.n = n

    @classmethod
    def fit(cls, samples: List[Tuple[float, bool]], bins: int = 10) -> "Calibrator":
        clean = [(max(0.0, min(1.0, c)), 1.0 if ok else 0.0) for c, ok in samples]
        if not clean:
            return cls([], 0)
        buckets: dict = {}
        for c, ok in clean:
            idx = min(bins - 1, int(c * bins))
            buckets.setdefault(idx, []).append((c, ok))
        points = []
        for idx in sorted(buckets):
            items = buckets[idx]
            mean_conf = sum(c for c, _ in items) / len(items)
            acc = sum(ok for _, ok in items) / len(items)
            points.append([mean_conf, acc, float(len(items))])
        return cls(_pav(points), len(clean))

    def predict(self, conf: float) -> float:
        a = self.anchors
        if not a:
            return max(0.0, min(1.0, conf))
        if conf <= a[0][0]:
            return a[0][1]
        if conf >= a[-1][0]:
            return a[-1][1]
        for i in range(1, len(a)):
            x0, y0 = a[i - 1]
            x1, y1 = a[i]
            if conf <= x1:
                t = 0.0 if x1 == x0 else (conf - x0) / (x1 - x0)
                return max(0.0, min(1.0, y0 + t * (y1 - y0)))
        return a[-1][1]

    def to_dict(self) -> dict:
        return {"anchors": [list(a) for a in self.anchors], "n": self.n}

    @classmethod
    def from_dict(cls, d: dict) -> "Calibrator":
        return cls([tuple(a) for a in d.get("anchors", [])], int(d.get("n", 0)))

    def save(self, path: Path = _CALIB_PATH) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = _CALIB_PATH) -> Optional["Calibrator"]:
        if not Path(path).is_file():
            return None
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Runtime entry point used by the pipeline
# --------------------------------------------------------------------------- #

_CACHED: Optional[Calibrator] = None
_LOADED = False


def get_calibrator() -> Optional[Calibrator]:
    global _CACHED, _LOADED
    if not _LOADED:
        _CACHED = Calibrator.load()
        _LOADED = True
    return _CACHED


def _conservative(raw: float) -> float:
    """No fitted map yet: shrink toward 0.5 so we under-claim rather than bluff."""
    raw = max(0.0, min(1.0, raw))
    return 0.5 + (raw - 0.5) * 0.9


def apply_calibration(label, raw_confidence: float) -> float:
    """Map a raw confidence to a calibrated one. Used by the pipeline and eval."""
    raw = max(0.0, min(1.0, raw_confidence))
    cal = get_calibrator()
    value = _conservative(raw) if cal is None else cal.predict(raw)
    # Honesty cap: a trust tool never asserts absolute certainty (or absolute impossibility).
    return max(0.02, min(0.99, value))
