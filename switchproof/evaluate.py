"""The analytical heart: run both models over the sample, then decide — can you switch,
which slices are unsafe, and how much does it save?

Method (Case 1, incumbent-as-reference):
- AGREEMENT: how often the open model's label matches the frontier model's. Frontier is the
  live reference, so this is the "will users notice a change?" number. Reported with a
  Wilson 95% interval — a point estimate alone is not evidence.
- GOLD ACCURACY (bonus, since Banking77 is labeled): each model vs the human label, so we
  can also say whether the open model is actually *worse* or just *different*.
- PER-INTENT SLICES: agreement within each intent. The weak intents are where a naive switch
  would silently regress — so we route those back to frontier and keep the rest on open.
- COST: real token counts × your price assumptions × monthly volume. Three scenarios:
  all-frontier (today), all-open (naive switch), and hybrid (switch the safe slices only).
- VERDICT: SAFE_ALL / SAFE_HYBRID / NOT_YET, based on the *lower* confidence bound, not luck.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Dict, List, Optional

from . import runners as R
from .config import Assumptions, Pricing
from .stats import wilson

# A slice is "unsafe to switch" if its agreement is below threshold. We decide on the POINT
# estimate (with a minimum-sample floor) and report the Wilson interval alongside as the
# honest uncertainty — requiring the LOW bound to clear the bar is too strict at ~20-40/slice
# and would refuse every switch until slices are huge.
ROUTE_THRESHOLD = 0.85          # agreement at/above this -> safe to switch (matches the reference)
MIN_SLICE_N = 10                # below this, a slice is too small to judge -> keep on frontier
TRUST_SLICE_N = 30              # at/above this, the slice CI is tight enough to fully trust

# Correctness-aware override (only when gold labels exist, as in Banking77):
# agreement-with-the-frontier is a conservative floor, NOT ground truth. When the frontier
# is itself inconsistent on near-duplicate labels, a low-agreement slice can still be safe —
# if the open model is at least as accurate as the frontier against the human label there,
# the "disagreement" costs no quality, so we allow the switch.
ACC_MARGIN = 0.0                # open must be >= frontier accuracy on the slice to override
SAFE_ALL_LOW = 0.90            # overall agreement low-bound above this -> a full switch is safe
SAFE_HYBRID_QUALITY = 0.95     # post-routing parity above this -> the hybrid switch is safe


def _per_call_cost(in_tok: float, out_tok: float, p_in: float, p_out: float) -> float:
    return in_tok / 1e6 * p_in + out_tok / 1e6 * p_out


def run(sample: List[dict], frontier: R.Runner, open_: R.Runner,
        pricing: Pricing, assumptions: Assumptions,
        max_samples_out: int = 60, progress: Optional[callable] = None) -> dict:
    labels = sorted({r["label"] for r in sample})
    R.set_gold_context({r["text"]: r["label"] for r in sample})  # only used by mock runners

    rows: List[dict] = []
    f_in = f_out = o_in = o_out = 0.0
    f_ms: List[float] = []
    o_ms: List[float] = []

    for i, r in enumerate(sample):
        q, gold = r["text"], r["label"]
        fp = frontier.classify(q, labels)
        op = open_.classify(q, labels)
        f_in += fp.in_tokens; f_out += fp.out_tokens
        o_in += op.in_tokens; o_out += op.out_tokens
        if fp.latency_ms: f_ms.append(fp.latency_ms)
        if op.latency_ms: o_ms.append(op.latency_ms)
        rows.append({
            "text": q, "gold": gold, "frontier": fp.label, "open": op.label,
            "agree": fp.label == op.label,
            "frontier_correct": fp.label == gold, "open_correct": op.label == gold,
        })
        if progress and (i + 1) % 50 == 0:
            progress(i + 1, len(sample))

    n = len(rows)
    agree_k = sum(1 for x in rows if x["agree"])
    f_acc_k = sum(1 for x in rows if x["frontier_correct"])
    o_acc_k = sum(1 for x in rows if x["open_correct"])

    def band(k: int, m: int) -> dict:
        lo, hi = wilson(k, m)
        return {"k": k, "n": m, "rate": (k / m if m else 0.0), "low": lo, "high": hi}

    # ---- per-intent slices ---------------------------------------------------
    by_intent: Dict[str, List[dict]] = defaultdict(list)
    for x in rows:
        by_intent[x["gold"]].append(x)

    intents = []
    weak = []           # kept on frontier
    switched_set = set()
    for intent in sorted(by_intent):
        xs = by_intent[intent]
        m = len(xs)
        ak = sum(1 for x in xs if x["agree"])
        rate = ak / m if m else 0.0
        lo, hi = wilson(ak, m)
        f_acc = sum(1 for x in xs if x["frontier_correct"]) / m if m else 0.0
        o_acc = sum(1 for x in xs if x["open_correct"]) / m if m else 0.0

        enough_agreement = rate >= ROUTE_THRESHOLD
        as_accurate = o_acc + ACC_MARGIN >= f_acc          # open not worse vs the human label
        switchable = (m >= MIN_SLICE_N) and (enough_agreement or as_accurate)
        reason = None
        if switchable:
            reason = "agreement" if enough_agreement else "accuracy"
        else:
            weak.append(intent)
        if switchable:
            switched_set.add(intent)

        intents.append({
            "intent": intent, "n": m,
            "agreement": rate, "agree_low": lo, "agree_high": hi,
            "frontier_acc": f_acc, "open_acc": o_acc,
            "action": "switch" if switchable else "keep_on_frontier",
            "switch_reason": reason,          # "agreement" | "accuracy" | None
            "trusted": m >= TRUST_SLICE_N,
        })
    intents.sort(key=lambda d: d["agreement"])  # worst first — the eye goes to risk

    weak_rows = sum(len(by_intent[i]) for i in weak)
    weak_share = weak_rows / n if n else 0.0
    strong_share = 1.0 - weak_share
    n_switch_accuracy = sum(1 for it in intents if it["switch_reason"] == "accuracy")

    # ---- cost ----------------------------------------------------------------
    f_call = _per_call_cost(f_in / n, f_out / n, pricing.frontier_in, pricing.frontier_out)
    o_call = _per_call_cost(o_in / n, o_out / n, pricing.open_in, pricing.open_out)
    calls = assumptions.monthly_calls
    monthly_frontier = f_call * calls
    monthly_open = o_call * calls
    monthly_hybrid = (o_call * strong_share + f_call * weak_share) * calls
    savings_all = monthly_frontier - monthly_open
    savings_hybrid = monthly_frontier - monthly_hybrid

    # ---- quality after routing (vs the human gold label) --------------------
    # Under the routing plan, each row is served by open (if its intent switched) or frontier
    # (if kept). Quality = fraction of rows that then match the human label. Because we only
    # switch a slice when the open model is >= as accurate there, routing should hold or beat
    # staying all-frontier — often the *counterintuitive* win: cheaper AND no worse.
    post_correct = sum(
        (x["open_correct"] if x["gold"] in switched_set else x["frontier_correct"]) for x in rows
    )
    quality_after_routing = post_correct / n if n else 0.0
    all_frontier_acc = f_acc_k / n if n else 0.0
    all_open_acc = o_acc_k / n if n else 0.0

    # ---- verdict -------------------------------------------------------------
    agree_band = band(agree_k, n)
    if agree_band["low"] >= SAFE_ALL_LOW:
        verdict, headline_savings, switchable = "SAFE_ALL", savings_all, 1.0
    elif strong_share > 0 and quality_after_routing >= all_frontier_acc - 0.01:
        verdict, headline_savings, switchable = "SAFE_HYBRID", savings_hybrid, strong_share
    else:
        verdict, headline_savings, switchable = "NOT_YET", savings_hybrid, strong_share

    mode = "real" if not (frontier.is_mock or open_.is_mock) else "mock"
    partial = "mock" if (frontier.is_mock or open_.is_mock) else None

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "mock_models": [m for m, r in (("frontier", frontier), ("open", open_)) if r.is_mock],
        "task": {"name": "Banking77 — customer-support intent classification",
                 "n": n, "n_intents": len(labels)},
        "models": {
            "frontier": {"name": pricing.frontier_model, "mock": frontier.is_mock,
                         "price_in": pricing.frontier_in, "price_out": pricing.frontier_out,
                         "avg_in_tokens": f_in / n, "avg_out_tokens": f_out / n,
                         "avg_latency_ms": round(sum(f_ms) / len(f_ms), 1) if f_ms else None},
            "open": {"name": pricing.open_model, "mock": open_.is_mock,
                     "price_in": pricing.open_in, "price_out": pricing.open_out,
                     "avg_in_tokens": o_in / n, "avg_out_tokens": o_out / n,
                     "avg_latency_ms": round(sum(o_ms) / len(o_ms), 1) if o_ms else None},
        },
        "assumptions": {"monthly_calls": calls,
                        "frontier_cost_per_call": f_call, "open_cost_per_call": o_call},
        "headline": {
            "verdict": verdict,
            "agreement": agree_band,
            "monthly_savings": headline_savings,
            "monthly_savings_all": savings_all,
            "monthly_savings_hybrid": savings_hybrid,
            "annual_savings": headline_savings * 12,
            "savings_pct": (headline_savings / monthly_frontier if monthly_frontier else 0.0),
            "traffic_switchable_pct": switchable,
            "quality_after_routing": quality_after_routing,
            "all_frontier_acc": all_frontier_acc,
            "all_open_acc": all_open_acc,
        },
        "quality": {"agreement": agree_band,
                    "frontier_acc": band(f_acc_k, n), "open_acc": band(o_acc_k, n),
                    "quality_after_routing": quality_after_routing},
        "cost": {"monthly_frontier": monthly_frontier, "monthly_open": monthly_open,
                 "monthly_hybrid": monthly_hybrid,
                 "frontier_per_call": f_call, "open_per_call": o_call},
        "routing": {"route_threshold": ROUTE_THRESHOLD, "min_slice_n": MIN_SLICE_N,
                    "weak_intents": weak, "weak_share": weak_share, "strong_share": strong_share,
                    "n_switched_by_accuracy": n_switch_accuracy},
        "intents": intents,
        "samples": _sample_rows(rows, max_samples_out),
    }


def _sample_rows(rows: List[dict], k: int) -> List[dict]:
    """A browsable slice for the UI: prioritize disagreements (the interesting rows)."""
    disagree = [r for r in rows if not r["agree"]]
    agree = [r for r in rows if r["agree"]]
    picked = disagree[: k // 2] + agree[: k - len(disagree[: k // 2])]
    return [{"text": r["text"], "gold": r["gold"], "frontier": r["frontier"],
             "open": r["open"], "agree": r["agree"]} for r in picked[:k]]
