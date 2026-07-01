"""Answer-level eval — testing on PARAGRAPHS, the way AI actually responds.

Single-claim eval (eval.py) tests the judge. This tests the WHOLE pipeline on realistic
multi-sentence answers: decompose the paragraph into claims, verify each, and check that
we (a) catch the embedded false claims, (b) never flag the true ones, (c) leave opinions
alone. This is the real-world test.

Each answer is annotated with `false_claims` (distinctive substrings that SHOULD be flagged)
and `true_claims` (substrings that must NOT be flagged). Matching is by substring against
the decomposed claim text — so annotations use distinctive phrases.

Run:  python -m second_opinion.answereval
      python -m second_opinion.answereval 3      # first 3 answers only
"""

from __future__ import annotations

import json
import os
import re
import sys

from .models import Label
from .pipeline import Pipeline
from .stats import wilson

_DIM = "\033[2m"
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_AMBER = "\033[33m"

_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "benchmark", "answers.jsonl")


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


_STOP = {"the", "a", "an", "is", "are", "of", "in", "on", "to", "and", "for", "with",
         "that", "this", "it", "its", "was", "were", "be", "as", "at", "by", "from"}


def _content_tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3 and w not in _STOP}


def _matches(substr, verdicts):
    """Match a verdict to an annotation by exact substring OR strong token overlap.

    Decomposition often rewords a planted claim ("...off the coast of Chile" -> "...one of
    South America's wonders"), so exact substring under-counts real catches. Token overlap
    recovers reworded matches while staying strict enough to avoid coincidental hits.
    """
    s = substr.lower()
    toks = _content_tokens(substr)
    need = max(1, (len(toks) + 1) // 2)  # at least half the distinctive tokens
    out = []
    for v in verdicts:
        ct = v.claim.text.lower()
        if s in ct or (toks and len(toks & _content_tokens(ct)) >= need):
            out.append(v)
    return out


def evaluate_answers(path: str, limit: int = None) -> dict:
    cases = _load(path)
    if limit:
        cases = cases[:limit]
    pipeline = Pipeline()
    mock = pipeline.judge.is_mock
    n = len(cases)
    print(f"{_DIM}Running {n} answers · {'MOCK' if mock else 'REAL (live web search)'}{_RESET}",
          file=sys.stderr, flush=True)

    rows = []
    tot_false = tot_caught = tot_true = tot_wrongflag = tot_spurious = tot_errors = 0
    for i, c in enumerate(cases, 1):
        print(f"{_DIM}  [{i}/{n}] {c['id']}: {c['answer'][:50]}…{_RESET}", file=sys.stderr, flush=True)
        report = pipeline.run(c["answer"])
        contradicted = [v for v in report.verdicts if v.label == Label.CONTRADICTED]
        tot_errors += sum(1 for v in report.verdicts if "Verification unavailable" in (v.rationale or ""))

        false_claims = c.get("false_claims", [])
        true_claims = c.get("true_claims", [])
        caught = [f for f in false_claims if _matches(f, contradicted)]
        missed = [f for f in false_claims if not _matches(f, contradicted)]
        wrongly_flagged = [t for t in true_claims if _matches(t, contradicted)]

        # Spurious = a CONTRADICTED verdict that matches no annotated claim at all.
        annotated = false_claims + true_claims
        spurious = [
            v.claim.text for v in contradicted
            if not any(a.lower() in v.claim.text.lower() for a in annotated)
        ]

        tot_false += len(false_claims)
        tot_caught += len(caught)
        tot_true += len(true_claims)
        tot_wrongflag += len(wrongly_flagged)
        tot_spurious += len(spurious)
        rows.append({
            "id": c["id"], "missed": missed, "wrongly_flagged": wrongly_flagged,
            "spurious": spurious, "n_false": len(false_claims), "caught": len(caught),
            "is_control": not false_claims,
        })

    return {
        "mock": mock, "n": n,
        "recall": tot_caught / tot_false if tot_false else 1.0,
        "tot_false": tot_false, "tot_caught": tot_caught,
        "false_flag_rate": tot_wrongflag / tot_true if tot_true else 0.0,
        "tot_true": tot_true, "tot_wrongflag": tot_wrongflag,
        "tot_spurious": tot_spurious, "tot_errors": tot_errors,
        "rows": rows,
    }


def render(res: dict) -> str:
    L = ["", f"{_BOLD}Second Opinion — Answer-Level Eval (paragraphs){_RESET}"]
    if res["mock"]:
        L.append(f"{_DIM}MOCK MODE — illustrative; embedded falses are KB-known. Real mode handles any.{_RESET}")
    L.append("")
    rlo, rhi = wilson(res["tot_caught"], res["tot_false"])
    flo, fhi = wilson(res["tot_wrongflag"], res["tot_true"])
    L.append(
        f"  {_BOLD}Caught {res['tot_caught']}/{res['tot_false']} embedded errors "
        f"({res['recall']*100:.0f}% recall, 95% CI {rlo*100:.0f}–{rhi*100:.0f}%){_RESET} across {res['n']} answers."
    )
    L.append(f"  false-flag on true claims: {res['tot_wrongflag']}/{res['tot_true']} "
             f"({res['false_flag_rate']*100:.0f}%, 95% CI {flo*100:.0f}–{fhi*100:.0f}%)")
    L.append(f"  spurious flags (unannotated): {res['tot_spurious']}   {_DIM}(may be real catches or noise){_RESET}")
    if res.get("tot_errors"):
        L.append(
            f"  {_AMBER}⚠ {res['tot_errors']} verification FAILURES (bad JSON / API) fell back to unverified — "
            f"plumbing, not judge misses. Some 'missed' errors may actually be these; re-run.{_RESET}"
        )
    L.append("")
    for r in res["rows"]:
        problems = []
        if r["missed"]:
            problems.append(f"{_RED}missed {r['missed']}{_RESET}")
        if r["wrongly_flagged"]:
            problems.append(f"{_RED}wrongly flagged TRUE {r['wrongly_flagged']}{_RESET}")
        if r["spurious"]:
            problems.append(f"{_AMBER}spurious {r['spurious']}{_RESET}")
        mark = f"{_GREEN}✓{_RESET}" if not problems else f"{_RED}✗{_RESET}"
        tag = " (control)" if r["is_control"] else f" — caught {r['caught']}/{r['n_false']}"
        L.append(f"  {mark} {r['id']}{tag}" + (("  " + "; ".join(problems)) if problems else ""))
    L.append("")
    return "\n".join(L)


def main(argv=None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    path = next((a for a in argv if a.endswith(".jsonl")), _DEFAULT)
    limit = next((int(a) for a in argv if a.isdigit()), None)
    print(render(evaluate_answers(path, limit=limit)))


if __name__ == "__main__":
    main()
