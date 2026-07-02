"""Mixed-answer eval — the case that actually matters in production.

Most real AI answers are non-factual scaffolding (advice, opinion) with a few load-bearing
factual claims embedded inside. The job: catch the embedded FALSE claim without flagging
the surrounding advice.

This runner sends whole answers through the full Pipeline (decompose -> judge) and measures:
  - catch rate     : of answers with a planted false claim, how many did we flag it in?
  - spurious flags : did we wrongly mark CONTRADICTED on the advice/wrapper?

Run:  python -m second_opinion.mixedeval
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
_GREEN = "\033[32m"
_RED = "\033[31m"
_AMBER = "\033[33m"

_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "benchmark", "mixed_answers.jsonl")


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def evaluate_mixed(path: str) -> dict:
    cases = _load(path)
    pipeline = Pipeline()
    rows = []
    for c in cases:
        report = pipeline.run(c["answer"])
        ef = (c.get("embedded_false") or "").lower().strip()
        contradicted = [v for v in report.verdicts if v.label == Label.CONTRADICTED]

        caught = bool(ef) and any(ef in v.claim.text.lower() for v in contradicted)
        # A spurious flag = we marked CONTRADICTED on something that ISN'T the planted error.
        spurious = [v for v in contradicted if not ef or ef not in v.claim.text.lower()]
        rows.append(
            {
                "id": c["id"],
                "has_planted": bool(ef),
                "caught": caught,
                "spurious": [v.claim.text for v in spurious],
                "is_control": not bool(ef),
            }
        )
    planted = [r for r in rows if r["has_planted"]]
    caught = sum(1 for r in planted if r["caught"])
    spurious_total = sum(len(r["spurious"]) for r in rows)
    return {
        "n": len(rows),
        "n_planted": len(planted),
        "caught": caught,
        "catch_rate": caught / len(planted) if planted else 0.0,
        "spurious_total": spurious_total,
        "rows": rows,
        "mock": Pipeline().judge.is_mock,
    }


def render(res: dict) -> str:
    L = ["", f"{_BOLD}Second Opinion — Mixed-Answer Eval{_RESET}"]
    if res["mock"]:
        L.append(f"{_DIM}MOCK MODE — illustrative; embedded falses are KB-known. Real mode handles any.{_RESET}")
    L.append("")
    L.append(
        f"  {_BOLD}Caught the embedded error in {res['caught']}/{res['n_planted']} "
        f"answers ({res['catch_rate']*100:.0f}%). Spurious flags on advice: {res['spurious_total']}.{_RESET}"
    )
    L.append("")
    for r in res["rows"]:
        if r["is_control"]:
            ok = not r["spurious"]
            mark = f"{_GREEN}✓{_RESET}" if ok else f"{_RED}✗{_RESET}"
            note = "left advice alone" if ok else f"WRONGLY flagged: {r['spurious']}"
            L.append(f"  {mark} {r['id']} (control) — {note}")
        else:
            mark = f"{_GREEN}✓{_RESET}" if r["caught"] else f"{_RED}✗{_RESET}"
            extra = f"  {_AMBER}+spurious {r['spurious']}{_RESET}" if r["spurious"] else ""
            L.append(f"  {mark} {r['id']} — {'caught embedded error' if r['caught'] else 'MISSED it'}{extra}")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    path = argv[0] if argv else _DEFAULT
    print(render(evaluate_mixed(path)))


if __name__ == "__main__":
    main()
