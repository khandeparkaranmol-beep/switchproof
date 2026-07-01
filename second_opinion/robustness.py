"""Run-to-run robustness — is a verdict trustworthy, or just lucky?

LLMs are non-deterministic, so a single run overstates reliability. This runs each claim
K times (cache OFF, so every call is fresh) and reports how often the verdict FLIPS. A
verdict that changes between runs isn't dependable even when it's often right.

    flip rate = fraction of claims whose K verdicts weren't all identical (lower is better)

Run:  python -m second_opinion.robustness benchmark/hard_mode.jsonl --k 3 --limit 15

Note: real mode makes K x N grounded calls (cost). Use --limit. Mock is deterministic (0% flips).
"""

from __future__ import annotations

import json
import os
import sys

# Force fresh calls: robustness needs independent samples, not the cache.
os.environ["SECOND_OPINION_NO_CACHE"] = "1"

from .models import Claim  # noqa: E402
from .providers import Judge  # noqa: E402
from .stats import wilson  # noqa: E402

_DIM = "\033[2m"; _RESET = "\033[0m"; _BOLD = "\033[1m"; _GREEN = "\033[32m"; _AMBER = "\033[33m"
_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "benchmark", "hard_cases.jsonl")


def _load(path, limit):
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    return rows[:limit] if limit else rows


def run(path, k=3, limit=15):
    import second_opinion.cache as _c
    _c._CACHE = None  # ensure the no-cache env takes effect
    cases = _load(path, limit)
    judge = Judge()
    n = len(cases)
    print(f"{_DIM}Robustness: {n} claims x {k} runs · {'MOCK' if judge.is_mock else 'REAL'}{_RESET}",
          file=sys.stderr, flush=True)
    rows = []
    for i, c in enumerate(cases, 1):
        labels = []
        for _ in range(k):
            label, _conf, _r, _e = judge.verify_routed(Claim(text=c["claim"]))
            labels.append(label.value)
        flipped = len(set(labels)) > 1
        print(f"{_DIM}[{i}/{n}] {'FLIP' if flipped else 'stable'}: {labels}  {c['claim'][:40]}{_RESET}",
              file=sys.stderr, flush=True)
        rows.append({"id": c["id"], "labels": labels, "flipped": flipped, "claim": c["claim"]})
    return {"is_mock": judge.is_mock, "k": k, "rows": rows}


def render(res):
    rows = res["rows"]
    n = len(rows)
    flips = sum(1 for r in rows if r["flipped"])
    rate = flips / n if n else 0.0
    lo, hi = wilson(flips, n)
    L = ["", f"{_BOLD}Second Opinion — Run-to-Run Robustness (k={res['k']}){_RESET}"]
    if res["is_mock"]:
        L.append(f"{_DIM}MOCK MODE — the canned judge is deterministic, so flips are always 0. Real mode is the test.{_RESET}")
    L.append("")
    tag = _GREEN + "stable" + _RESET if rate <= 0.1 else _AMBER + "unstable" + _RESET
    L.append(f"  {_BOLD}Flip rate: {rate*100:.0f}% ({flips}/{n})  95% CI {lo*100:.0f}–{hi*100:.0f}%{_RESET}  [{tag}]")
    L.append(f"  {_DIM}(fraction of claims whose verdict changed across {res['k']} runs — lower is more dependable){_RESET}")
    if flips:
        L.append("")
        L.append(f"{_BOLD}Flipped:{_RESET}")
        for r in rows:
            if r["flipped"]:
                L.append(f"  {_AMBER}{r['labels']}{_RESET}  {r['claim'][:60]}")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = next((a for a in argv if a.endswith(".jsonl")), _DEFAULT)
    k = 3
    limit = 15
    if "--k" in argv:
        k = int(argv[argv.index("--k") + 1])
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    print(render(run(path, k=k, limit=limit)))


if __name__ == "__main__":
    main()
