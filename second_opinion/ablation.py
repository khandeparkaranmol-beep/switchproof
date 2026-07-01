"""Baselines and ablations — proving WHY grounded verification works, and where the lift comes from.

An accuracy number in isolation is just a number. This harness runs the same benchmark under
three modes and decomposes the result:

  1. self-critique   — ask the model "is this true?" from its own knowledge, no search, no
                       careful prompt. This is the "can't the model just check itself?" baseline.
  2. no-retrieval    — our careful, conservative judge prompt, but with web search OFF.
                       Isolates the value of prompting alone.
  3. grounded        — the full product: careful prompt + live web search.

Deltas that tell the story:
  no-retrieval − self-critique  = value of careful PROMPTING
  grounded − no-retrieval       = value of RETRIEVAL (the core thesis)
  grounded − self-critique      = total system lift, with a McNemar significance test.

Run:  python -m second_opinion.ablation
      python -m second_opinion.ablation 40      # first 40 claims
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

from .cache import cache_key, get_cache
from .models import Claim, Label
from .providers import _JUDGE_MODEL, _WEB_SEARCH_TOOL, _diagnose, _extract_json, JudgeError, Judge
from .stats import wilson

_DIM = "\033[2m"; _RESET = "\033[0m"; _BOLD = "\033[1m"; _GREEN = "\033[32m"; _AMBER = "\033[33m"
_BENCH = os.path.join(os.path.dirname(__file__), "..", "benchmark", "hard_cases.jsonl")

MODES = ["self_critique", "no_retrieval", "grounded"]
_LABELS = {"self_critique": "self-critique (no search, naive)",
           "no_retrieval": "no-retrieval (our prompt, no search)",
           "grounded": "grounded (prompt + web search)"}

_SELF_CRITIQUE_SYS = (
    "You are a knowledgeable assistant. Judge whether the claim is true or false using only "
    "your own knowledge. Do not overthink calibration — just answer as you normally would."
)
_CAREFUL_SYS = (
    "You are an independent fact-checker judging a SINGLE claim. Labels: SUPPORTED, CONTRADICTED, "
    "UNVERIFIED, NOT_CHECKABLE. A false alarm is worse than a miss: only CONTRADICTED when you are "
    "confident the claim is false; if evidence is thin, mixed, contested, or merely surprising, "
    "return UNVERIFIED. Your confidence must reflect real uncertainty."
)
_USER = ('CLAIM: {c}\n\nRespond with ONLY a JSON object: '
         '{{"label":"supported|contradicted|unverified|not_checkable","confidence":0.0-1.0,'
         '"rationale":"one sentence"}}')


def _load(path, split=None, limit=None):
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    rows = [r for r in rows if r["gold"] in ("contradicted", "supported")]  # binary true/false set
    if split:
        rows = [r for r in rows if r.get("split") == split]
    if limit:
        rows = rows[:limit]
    return rows


def _llm_mode(client, mode, claim):
    """self_critique / no_retrieval verdict (no web search), cached per mode."""
    key = cache_key(_JUDGE_MODEL, mode + "::" + claim.text)
    cache = get_cache()
    hit = cache.get(key)
    if hit:
        return Label(hit["label"]), float(hit["confidence"])
    system = _SELF_CRITIQUE_SYS if mode == "self_critique" else _CAREFUL_SYS
    try:
        msg = client.messages.create(
            model=_JUDGE_MODEL, max_tokens=500, system=system,
            messages=[{"role": "user", "content": _USER.format(c=claim.text)}],
        )
    except Exception as exc:  # noqa: BLE001
        raise _diagnose(exc)
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    data = _extract_json(text) or {}
    try:
        label = Label(str(data.get("label", "unverified")).strip().lower())
    except ValueError:
        label = Label.UNVERIFIED
    try:
        conf = float(data.get("confidence", 0.4))
    except (TypeError, ValueError):
        conf = 0.4
    cache.put(key, {"label": label.value, "confidence": conf})
    return label, conf


def _verify(judge, client, mode, claim, is_mock):
    if is_mock:  # mock has no real modes; run the KB judge so the harness is testable
        lbl, conf, _r, _e = judge.judge(claim, [])
        return lbl, conf
    if mode == "grounded":
        lbl, conf, _r, _e = judge.judge(claim, [])  # real product path (with search, cached)
        return lbl, conf
    return _llm_mode(client, mode, claim)


def _mcnemar(pair_correct):
    """pair_correct: list of (grounded_correct, self_correct). Returns (stat, p) via chi-sq df=1."""
    b = sum(1 for g, s in pair_correct if g and not s)   # grounded right, self wrong
    c = sum(1 for g, s in pair_correct if s and not g)   # self right, grounded wrong
    if b + c == 0:
        return 0.0, 1.0, b, c
    stat = (abs(b - c) - 1) ** 2 / (b + c)               # continuity-corrected
    p = math.erfc(math.sqrt(stat / 2))                   # chi-square df=1 survival
    return stat, p, b, c


def run(path, limit=None):
    cases = _load(path, limit=limit)
    judge = Judge()
    is_mock = judge.is_mock
    client = None
    if not is_mock:
        from anthropic import Anthropic
        client = Anthropic()

    n = len(cases)
    print(f"{_DIM}Ablation over {n} true/false claims · {'MOCK' if is_mock else 'REAL'}{_RESET}",
          file=sys.stderr, flush=True)

    # results[mode] = list of dicts {id, gold, pred, correct}
    results = {m: [] for m in MODES}
    for i, c in enumerate(cases, 1):
        claim = Claim(text=c["claim"])
        print(f"{_DIM}[{i}/{n}] {c['claim'][:56]}{_RESET}", file=sys.stderr, flush=True)
        for m in MODES:
            try:
                label, _conf = _verify(judge, client, m, claim, is_mock)
            except JudgeError as err:
                label = Label.UNVERIFIED
            results[m].append({"id": c["id"], "gold": c["gold"], "pred": label.value,
                               "correct": label.value == c["gold"]})

    return {"n": n, "is_mock": is_mock, "results": results}


def _metrics(recs):
    false_items = [r for r in recs if r["gold"] == "contradicted"]
    true_items = [r for r in recs if r["gold"] == "supported"]
    caught = sum(1 for r in false_items if r["pred"] == "contradicted")
    ff = sum(1 for r in true_items if r["pred"] == "contradicted")
    correct = sum(1 for r in recs if r["correct"])
    return {
        "catch": caught / len(false_items) if false_items else 0.0,
        "catch_ci": wilson(caught, len(false_items)),
        "ff": ff / len(true_items) if true_items else 0.0,
        "ff_ci": wilson(ff, len(true_items)),
        "acc": correct / len(recs) if recs else 0.0,
        "acc_ci": wilson(correct, len(recs)),
    }


def render(res):
    L = ["", f"{_BOLD}Second Opinion — Baselines & Ablation{_RESET}"]
    if res["is_mock"]:
        L.append(f"{_DIM}MOCK MODE — all three modes use the canned judge, so they'll match. "
                 f"Set ANTHROPIC_API_KEY for the real comparison.{_RESET}")
    L.append("")
    def pct(x): return f"{x*100:.0f}%"
    m = {mode: _metrics(res["results"][mode]) for mode in MODES}

    L.append(f"  {'mode':<38} {'catch':>16}   {'false-flag':>15}   {'overall':>15}")
    for mode in MODES:
        x = m[mode]
        catch = f"{pct(x['catch'])} ({pct(x['catch_ci'][0])}-{pct(x['catch_ci'][1])})"
        ff = f"{pct(x['ff'])} ({pct(x['ff_ci'][0])}-{pct(x['ff_ci'][1])})"
        acc = f"{pct(x['acc'])} ({pct(x['acc_ci'][0])}-{pct(x['acc_ci'][1])})"
        L.append(f"  {_LABELS[mode]:<38} {catch:>16}   {ff:>15}   {acc:>15}")

    prompting = m["no_retrieval"]["acc"] - m["self_critique"]["acc"]
    retrieval = m["grounded"]["acc"] - m["no_retrieval"]["acc"]
    total = m["grounded"]["acc"] - m["self_critique"]["acc"]
    pair = list(zip([r["correct"] for r in res["results"]["grounded"]],
                    [r["correct"] for r in res["results"]["self_critique"]]))
    stat, p, b, c = _mcnemar(pair)

    L.append("")
    L.append(f"{_BOLD}Where the accuracy comes from{_RESET}")
    L.append(f"  value of careful prompting  (no-retrieval − self-critique):  {_GREEN}{prompting*100:+.0f} pts{_RESET}")
    L.append(f"  value of RETRIEVAL          (grounded − no-retrieval):       {_GREEN}{retrieval*100:+.0f} pts{_RESET}")
    L.append(f"  total system lift           (grounded − self-critique):      {_GREEN}{total*100:+.0f} pts{_RESET}")
    sig = "significant" if p < 0.05 else "not significant (need more data)"
    L.append(f"  {_DIM}McNemar grounded vs self-critique: {b} gained, {c} lost, p={p:.4f} — {sig}.{_RESET}")
    L.append("")
    L.append(f"{_DIM}Reading: if 'value of retrieval' is large, grounding does the work (the thesis holds). "
             f"If self-critique is already high, the benchmark is too easy / memorised — make it harder.{_RESET}")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = next((a for a in argv if a.endswith(".jsonl")), _BENCH)
    limit = next((int(a) for a in argv if a.isdigit()), None)
    print(render(run(path, limit=limit)))


if __name__ == "__main__":
    main()
