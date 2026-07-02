"""Verify the verifier.

Runs Second Opinion over a benchmark of hard cases and reports the numbers that make
this a trust product instead of a vibe:

- catch rate      : of consequential errors, how many did we flag as CONTRADICTED?
- false-flag rate : of true claims, how many did we wrongly flag?
- opinion handling : did we correctly leave judgments un-checked?
- calibration (ECE): when we say "90% confident", are we right 90% of the time?
- per-category breakdown + blind spots: WHERE are we blind? (the diagnostic that matters)

Run:  python -m second_opinion.eval
      python -m second_opinion.eval benchmark/hard_cases.jsonl
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List

from .models import Claim, Label
from .pipeline import _calibrate
from .providers import Judge, classify_route
from .stats import wilson

_DIM = "\033[2m"
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_AMBER = "\033[33m"
_RED = "\033[31m"

_DEFAULT_SET = os.path.join(os.path.dirname(__file__), "..", "benchmark", "hard_cases.jsonl")


def _load(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _ece(records: List[dict], bins: int = 10) -> float:
    """Expected Calibration Error over items where we made a confident call."""
    scored = [r for r in records if r["pred"] in ("supported", "contradicted", "unverified")]
    if not scored:
        return 0.0
    buckets: Dict[int, List[dict]] = defaultdict(list)
    for r in scored:
        idx = min(bins - 1, int(r["confidence"] * bins))
        buckets[idx].append(r)
    total = len(scored)
    ece = 0.0
    for items in buckets.values():
        avg_conf = sum(i["confidence"] for i in items) / len(items)
        acc = sum(1 for i in items if i["correct"]) / len(items)
        ece += (len(items) / total) * abs(avg_conf - acc)
    return ece


_HIGH_SEV_KW = ("vaccine", "cancer", "medication", "dose", "disease", "cure", "poison",
                "suicide", "overdose", "symptom", "diagnos", "tax", "invest", "lawsuit",
                "court", "legal", "contract", "fatal", "toxic", "allerg", "drug", "surgery")


def _severity(row: dict) -> float:
    """How much a MISS on this claim would hurt. Explicit 'severity' wins; else a heuristic."""
    if "severity" in row:
        try:
            return float(row["severity"])
        except (TypeError, ValueError):
            pass
    cat, text = row.get("category", ""), row.get("claim", "").lower()
    if cat == "fabricated_citation" or any(k in text for k in _HIGH_SEV_KW):
        return 3.0
    if cat in ("false_causal", "numeric", "plausible_fabrication", "citation"):
        return 2.0
    return 1.0


def evaluate(path: str, split: str = None, limit: int = None) -> dict:
    cases = _load(path)
    if split:
        cases = [c for c in cases if c.get("split") == split]
    if limit:
        cases = cases[:limit]
    judge = Judge()

    mode = "MOCK" if judge.is_mock else "REAL (live web search — ~10-20s per claim)"
    n = len(cases)
    print(f"{_DIM}Running {n} cases · {mode}{_RESET}", file=sys.stderr, flush=True)

    records = []
    for i, c in enumerate(cases, 1):
        claim = Claim(text=c["claim"])
        print(f"{_DIM}[{i}/{n}] {claim.text[:64]}{_RESET}", file=sys.stderr, flush=True)
        # Route like the product: each claim to its specialized checker.
        route = classify_route(claim.text)
        if route == "citation":
            label, raw_conf, rationale, _ev = judge.verify_citation(claim)
        elif route == "temporal":
            label, raw_conf, rationale, _ev = judge.verify_temporal(claim)
        elif route == "numeric":
            label, raw_conf, rationale, _ev = judge.verify_numeric(claim)
        else:
            label, raw_conf, rationale, _ev = judge.judge(claim, [])
        conf = _calibrate(label, raw_conf)
        hit = "✓" if label.value == c["gold"] else "·"
        print(f"{_DIM}      {hit} {label.value} ({conf:.2f}){_RESET}", file=sys.stderr, flush=True)
        gold = c["gold"]
        records.append(
            {
                "id": c["id"],
                "category": c["category"],
                "gold": gold,
                "pred": label.value,
                "confidence": conf,
                "correct": label.value == gold,
                "claim": c["claim"],
                "severity": _severity(c),
                # A plumbing failure (bad JSON / API error) that fell back to unverified —
                # NOT a genuine judge miss. Surfaced so it can't silently deflate the score.
                "error": "Verification unavailable" in (rationale or ""),
            }
        )

    false_items = [r for r in records if r["gold"] == "contradicted"]
    true_items = [r for r in records if r["gold"] == "supported"]
    opinion_items = [r for r in records if r["gold"] == "not_checkable"]

    caught = sum(1 for r in false_items if r["pred"] == "contradicted")
    false_flags = sum(1 for r in true_items if r["pred"] == "contradicted")
    opinions_ok = sum(1 for r in opinion_items if r["pred"] == "not_checkable")

    # Harm-weighted catch: a missed dangerous claim costs more than a missed trivia error.
    sev_total = sum(r["severity"] for r in false_items)
    sev_caught = sum(r["severity"] for r in false_items if r["pred"] == "contradicted")
    weighted_catch = sev_caught / sev_total if sev_total else 0.0
    high_sev_misses = sum(1 for r in false_items if r["pred"] != "contradicted" and r["severity"] >= 3)

    catch_rate = caught / len(false_items) if false_items else 0.0
    false_flag_rate = false_flags / len(true_items) if true_items else 0.0
    opinion_acc = opinions_ok / len(opinion_items) if opinion_items else 0.0
    ece = _ece(records)

    # Per-category catch (for false categories) / accuracy.
    by_cat: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        by_cat[r["category"]].append(r)

    return {
        "judge_is_mock": judge.is_mock,
        "n": len(records),
        "catch_rate": catch_rate,
        "false_flag_rate": false_flag_rate,
        "opinion_accuracy": opinion_acc,
        "ece": ece,
        "caught": caught,
        "n_false": len(false_items),
        "false_flags": false_flags,
        "n_true": len(true_items),
        "weighted_catch": weighted_catch,
        "high_sev_misses": high_sev_misses,
        "errors": sum(1 for r in records if r["error"]),
        "by_category": {k: v for k, v in by_cat.items()},
        "records": records,
    }


def _cat_catch(items: List[dict]) -> str:
    """A short caught/total or correct/total string for a category."""
    golds = {i["gold"] for i in items}
    if golds == {"contradicted"}:
        c = sum(1 for i in items if i["pred"] == "contradicted")
        return f"{c}/{len(items)} caught"
    ok = sum(1 for i in items if i["correct"])
    return f"{ok}/{len(items)} correct"


def render(res: dict) -> str:
    L = []
    L.append("")
    L.append(f"{_BOLD}Second Opinion — Verifier Scorecard{_RESET}")
    if res["judge_is_mock"]:
        L.append(
            f"{_DIM}MOCK MODE — illustrative numbers from a canned judge. They demonstrate the "
            f"harness, not real accuracy. Set ANTHROPIC_API_KEY + wire retrieval for real numbers.{_RESET}"
        )
    L.append("")

    def pct(x):
        return f"{x*100:.0f}%"

    headline = (
        f"Caught {pct(res['catch_rate'])} of consequential errors "
        f"({res['caught']}/{res['n_false']}) at a {pct(res['false_flag_rate'])} false-flag rate. "
        f"ECE {res['ece']:.2f}."
    )
    L.append(f"  {_BOLD}{headline}{_RESET}")
    if res["n_false"] < 30:
        L.append(
            f"  {_AMBER}⚠ small sample (n={res['n_false']} error cases) — treat as directional, "
            f"not a published number. Grow toward a credible minimum before optimizing.{_RESET}"
        )
    if res.get("errors"):
        L.append(
            f"  {_AMBER}⚠ {res['errors']} verification FAILURES (bad JSON / API) counted as unverified — "
            f"these are plumbing, not judge misses. True catch rate is likely higher; re-run.{_RESET}"
        )
    L.append("")
    clo, chi = wilson(res["caught"], res["n_false"])
    flo, fhi = wilson(res["false_flags"], res["n_true"])
    L.append(f"  catch rate        {pct(res['catch_rate'])}   {_DIM}95% CI {pct(clo)}–{pct(chi)} (n={res['n_false']}){_RESET}")
    hi = f"   {_RED}{res['high_sev_misses']} high-severity miss(es){_RESET}" if res.get("high_sev_misses") else ""
    L.append(f"  harm-weighted     {pct(res.get('weighted_catch', 0))}   {_DIM}(misses weighted by how much they'd hurt){_RESET}{hi}")
    L.append(f"  false-flag rate   {pct(res['false_flag_rate'])}   {_DIM}95% CI {pct(flo)}–{pct(fhi)} (n={res['n_true']}){_RESET}")
    L.append(f"  opinion handling  {pct(res['opinion_accuracy'])}   {_DIM}(left judgments un-checked){_RESET}")
    L.append(f"  calibration (ECE) {res['ece']:.2f}   {_DIM}(lower = confidence means what it says){_RESET}")
    L.append("")

    L.append(f"{_BOLD}By category{_RESET}")
    for cat, items in sorted(res["by_category"].items()):
        line = _cat_catch(items)
        # flag blind spots in false categories
        blind = items[0]["gold"] == "contradicted" and any(i["pred"] != "contradicted" for i in items)
        marker = f"{_RED}← blind spot{_RESET}" if blind else ""
        L.append(f"  {cat:<20} {line}  {marker}")

    # Blind-spot narrative — the diagnostic that motivates the next build.
    blind_cats = [
        cat for cat, items in res["by_category"].items()
        if items[0]["gold"] == "contradicted" and any(i["pred"] != "contradicted" for i in items)
    ]
    if blind_cats:
        L.append("")
        L.append(f"{_BOLD}Where it's blind (next to fix){_RESET}")
        L.append(
            f"  {_AMBER}{', '.join(sorted(blind_cats))}{_RESET} — these need real source retrieval / "
            f"source-existence checks. Exactly the hard cases that make the product indispensable."
        )

    # Exactly what it got wrong — so you can inspect it, not just see a rate.
    wrong = [r for r in res.get("records", []) if not r["correct"]]
    if wrong:
        L.append("")
        L.append(f"{_BOLD}Misclassified — inspect these{_RESET}")
        for r in wrong[:12]:
            kind = ""
            if r["gold"] == "supported" and r["pred"] == "contradicted":
                kind = f"{_RED}FALSE-FLAG (cried wolf on a true claim){_RESET}"
            elif r["gold"] == "contradicted" and r["pred"] != "contradicted":
                kind = f"{_AMBER}MISS{_RESET}"
            else:
                kind = f"{_DIM}{r['gold']}→{r['pred']}{_RESET}"
            L.append(f"  [{r['id']}] {kind}")
            L.append(f"       {_DIM}{r['claim']}{_RESET}")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    path = next((a for a in argv if a.endswith(".jsonl")), _DEFAULT_SET)
    split = next((a for a in argv if a in ("dev", "test")), None)
    limit = next((int(a) for a in argv if a.isdigit()), None)
    res = evaluate(path, split=split, limit=limit)
    print(render(res))

    # Persist a machine-readable scorecard.
    out = os.path.join(os.path.dirname(path), "last_results.json")
    try:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in res.items() if k != "by_category"}, fh, indent=2)
        print(f"{_DIM}Full results written to {out}{_RESET}\n")
    except OSError:
        pass


if __name__ == "__main__":
    main()
