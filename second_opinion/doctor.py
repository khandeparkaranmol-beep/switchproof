"""Real-mode self-check — a diagnostic that's honest about what it's doing and what failed.

    python -m second_opinion.doctor

What it does, in order:
  1. Reports whether a key is loaded (and from where).
  2. Makes ONE live verification call and tells you, plainly, if the connection is broken
     and how to fix it (bad key, rate limit, wrong web_search tool id, network).
  3. Runs a couple of grounded checks, separating two DIFFERENT questions:
       - health:   did we get a grounded, sourced verdict back? (this is what 'working' means)
       - accuracy: did the verdict match a rough expected label? (a soft hint, never a failure)
  4. Reports latency so you can estimate how long the full eval will take.
"""

from __future__ import annotations

import sys
import time

from .models import Claim
from .providers import Judge, JudgeError, _JUDGE_MODEL, _WEB_SEARCH_TOOL

# (claim, rough expected label). Expected is only a sanity hint — verdicts are
# probabilistic, so a mismatch is reported as a note, never as a failure.
_CHECKS = [
    ("The Eiffel Tower is 450 metres tall.", "contradicted"),
    ("Paris is the capital of France.", "supported"),
]

_RULE = "-" * 60


def _run_one(judge: Judge, claim_text: str):
    """Run one real check, timed. Returns (label, conf, rationale, evidence, seconds).
    Lets JudgeError propagate so the caller can surface the real failure."""
    start = time.time()
    label, conf, rationale, evidence = judge.check(Claim(text=claim_text))
    return label, conf, rationale, evidence, time.time() - start


def _fail(err: JudgeError) -> None:
    print(f"\n  ✗ Connection FAILED: {err}  [{err.kind}]")
    if err.hint:
        print(f"    → {err.hint}")
    print("\nReal mode is NOT working yet. Fix the above and re-run: python -m second_opinion.doctor")
    sys.exit(1)


def main() -> None:
    print("Second Opinion — real-mode self-check\n")
    judge = Judge()

    # 1) Key / mode -------------------------------------------------------------
    if judge.is_mock:
        print("[mode] MOCK — no ANTHROPIC_API_KEY loaded, so real verification is OFF.")
        print("       Put your key in .env:  ANTHROPIC_API_KEY=sk-ant-...")
        print("       Then re-run:           python -m second_opinion.doctor")
        sys.exit(1)
    print(f"[config] model = {_JUDGE_MODEL}   web tool = {_WEB_SEARCH_TOOL}")

    # 2) Connectivity — ONE live call, with the real error surfaced -------------
    print("\n[1/2] Checking the connection (one live web search, ~10-30s)…", flush=True)
    try:
        label, conf, rationale, evidence, secs = _run_one(judge, _CHECKS[0][0])
    except JudgeError as err:
        _fail(err)

    print(f"  ✓ Connected — got a verdict in {secs:.1f}s.")
    if not evidence:
        print("  ⚠ But no sources came back — grounding looks weak (check the web_search tool).")
    results = [(_CHECKS[0], label, conf, rationale, evidence, secs)]

    # 3) Remaining grounded checks ---------------------------------------------
    for idx, (claim_text, expected) in enumerate(_CHECKS[1:], start=2):
        print(f"\n[{idx}/{len(_CHECKS)}] Checking: {claim_text} …", flush=True)
        try:
            label, conf, rationale, evidence, secs = _run_one(judge, claim_text)
        except JudgeError as err:
            _fail(err)
        print(f"  ✓ got a verdict in {secs:.1f}s.")
        results.append(((claim_text, expected), label, conf, rationale, evidence, secs))

    # 4) Report: health first, accuracy as a soft note --------------------------
    print("\n" + _RULE)
    print("RESULTS\n")
    latencies = []
    accuracy_notes = []
    all_grounded = True
    for (claim_text, expected), label, conf, rationale, evidence, secs in results:
        latencies.append(secs)
        grounded = "grounded" if evidence else "NO SOURCES"
        if not evidence:
            all_grounded = False
        print(f"  • {claim_text}")
        print(f"      verdict: {label.value} ({conf:.2f})   {secs:.1f}s   [{grounded}]")
        print(f"      why: {rationale}")
        for ev in evidence[:2]:
            print(f"      - {ev.source_title} — {ev.source_url}")
        print()
        if label.value != expected:
            accuracy_notes.append((claim_text, expected, label.value))

    avg = sum(latencies) / len(latencies)
    full = avg * 33 / 60  # 33 cases in the benchmark
    print(_RULE)
    health = "HEALTHY" if all_grounded else "WORKING, but grounding looks weak"
    print(f"Connection: {health} — real, grounded verification is live.")
    print(f"Latency: ~{avg:.0f}s per claim  →  full 33-case eval ≈ {full:.0f}-{full*1.5:.0f} min.")

    if accuracy_notes:
        print("\nNote (NOT a failure — verdicts are probabilistic; 'expected' is only a hint):")
        for claim_text, expected, got in accuracy_notes:
            print(f"  - \"{claim_text}\" — expected {expected}, got {got}")

    print("\nNext:  python -m second_opinion.eval")


if __name__ == "__main__":
    main()
