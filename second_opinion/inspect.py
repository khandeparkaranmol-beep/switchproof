"""Inspect exactly what the pipeline did to one answer — the diagnostic for a miss.

    python -m second_opinion.inspect ans-005        # a benchmark answer by id
    python -m second_opinion.inspect "some text..."  # or any raw text

Prints every claim decomposition pulled out of the answer and the verdict on each, so you
can see WHETHER a "missed" embedded error was actually caught but reworded (a measurement
artifact) or genuinely slipped through (a real gap).
"""

from __future__ import annotations

import json
import os
import sys

from .models import Label
from .pipeline import Pipeline

_DIM = "\033[2m"
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"

_ANS = os.path.join(os.path.dirname(__file__), "..", "benchmark", "answers.jsonl")


def _load():
    if not os.path.isfile(_ANS):
        return []
    with open(_ANS, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print("Usage: python -m second_opinion.inspect <answer_id | raw text>")
        sys.exit(1)

    case = next((c for c in _load() if c["id"] == argv[0]), None)
    answer = case["answer"] if case else " ".join(argv)

    print(f"\n{_BOLD}ANSWER{_RESET}\n{answer}\n")
    report = Pipeline().run(answer)

    print(f"{_BOLD}CLAIMS DECOMPOSITION PULLED OUT, AND EACH VERDICT{_RESET}")
    if not report.verdicts:
        print(f"  {_DIM}(none — decomposition produced no claims){_RESET}")
    for v in report.verdicts:
        color = _RED if v.label == Label.CONTRADICTED else ""
        print(f"  [{color}{v.label.value:13}{_RESET}] {int(v.confidence*100):3}%  {v.claim.text}")
        if v.rationale:
            print(f"        {_DIM}{v.rationale[:120]}{_RESET}")
        if v.evidence:
            e = v.evidence[0]
            print(f"        {_DIM}↳ {e.source_title} — {e.source_url}{_RESET}")

    if case:
        print(f"\n{_BOLD}ANNOTATION CHECK{_RESET}")
        for f in case.get("false_claims", []):
            matches = [v for v in report.verdicts if f.lower() in v.claim.text.lower()]
            caught = [v for v in matches if v.label == Label.CONTRADICTED]
            errored = [v for v in matches if "Verification unavailable" in (v.rationale or "")]
            if caught:
                print(f"  {_GREEN}CAUGHT{_RESET}  '{f}'")
            elif errored:
                print(f"  {_RED}NOT A REAL MISS{_RESET} '{f}' — extracted and matched, but the verdict call "
                      f"FAILED (plumbing): {errored[0].rationale[:90]}")
            elif matches:
                print(f"  {_RED}JUDGE GAP{_RESET} '{f}' — extracted, but judged [{matches[0].label.value}] "
                      f"instead of contradicted.")
            else:
                related = [v for v in report.verdicts if any(w in v.claim.text.lower() for w in f.lower().split() if len(w) > 3)]
                if related:
                    print(f"  {_RED}MATCH ARTIFACT{_RESET} '{f}' — surfaced under different wording (fix the matcher):")
                    for v in related:
                        print(f"         [{v.label.value}] {v.claim.text}")
                else:
                    print(f"  {_RED}EXTRACTION GAP{_RESET} '{f}' — decomposition didn't surface it at all.")
    print()


if __name__ == "__main__":
    main()
