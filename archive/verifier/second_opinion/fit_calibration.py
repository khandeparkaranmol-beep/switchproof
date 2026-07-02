"""Fit the calibration map — and prove it on held-out data.

    python -m second_opinion.fit_calibration

Fits the confidence->accuracy map on the DEV split and reports calibration error (ECE)
on the untouched TEST split, before vs after. Fitting and evaluating on different splits
is the whole point: otherwise the "we're calibrated" claim is circular.

In real mode this runs the grounded judge over the benchmark (one web search per claim),
so it costs API calls and a few minutes. In mock mode it's instant and illustrative.
"""

from __future__ import annotations

import json
import os
import sys

from .calibration import Calibrator, ece
from .models import Claim, Label
from .providers import Judge

_DIM = "\033[2m"
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"

_BENCH = os.path.join(os.path.dirname(__file__), "..", "benchmark", "hard_cases.jsonl")


def _load(path: str, split: str):
    with open(path, "r", encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    return [c for c in cases if c.get("split") == split]


def _collect(cases, judge: Judge, label: str):
    """Run the judge over cases -> (raw_confidence, correct) pairs, excluding opinions."""
    pairs = []
    n = len(cases)
    mode = "MOCK" if judge.is_mock else "REAL (live web search)"
    print(f"{_DIM}[{label}] {n} cases · {mode}{_RESET}", file=sys.stderr, flush=True)
    for i, c in enumerate(cases, 1):
        print(f"{_DIM}  [{i}/{n}] {c['claim'][:56]}{_RESET}", file=sys.stderr, flush=True)
        lbl, raw_conf, _r, _e = judge.judge(Claim(text=c["claim"]), [])
        if lbl == Label.NOT_CHECKABLE:
            continue  # opinions carry no factual-confidence to calibrate
        pairs.append((raw_conf, lbl.value == c["gold"]))
    return pairs


def main() -> None:
    judge = Judge()
    dev = _load(_BENCH, "dev")
    test = _load(_BENCH, "test")

    dev_pairs = _collect(dev, judge, "fit/dev")
    cal = Calibrator.fit(dev_pairs)
    cal.save()

    test_pairs = _collect(test, judge, "eval/test")
    before = ece(test_pairs)
    after = ece([(cal.predict(c), ok) for c, ok in test_pairs])

    print()
    print(f"{_BOLD}Calibration fit{_RESET}")
    if judge.is_mock:
        print(f"{_DIM}MOCK MODE — illustrative. Run with a real key for real calibration.{_RESET}")
    print(f"  fit on dev:   {len(dev_pairs)} checkable claims")
    print(f"  test on:      {len(test_pairs)} held-out claims")
    print()
    print(f"  ECE before (raw):        {before:.3f}")
    arrow = "↓ better" if after < before else ("→ no change" if after == before else "↑ worse")
    print(f"  ECE after (calibrated):  {after:.3f}   {_GREEN}{arrow}{_RESET}")
    print()
    print(f"{_BOLD}Learned map (raw confidence → calibrated){_RESET}")
    if not cal.anchors:
        print(f"  {_DIM}(no anchors — not enough data){_RESET}")
    for x, y in cal.anchors:
        print(f"  {x:.2f}  →  {y:.2f}")
    print()
    print(f"{_DIM}Saved to benchmark/calibration.json — eval and the CLI now use it automatically.{_RESET}")
    print(f"Next:  python -m second_opinion.eval   {_DIM}(ECE should now reflect the fitted map){_RESET}")


if __name__ == "__main__":
    main()
