"""One command. One report card. The whole evaluation.

    python -m second_opinion.report            # core: detection, calibration, honesty
    python -m second_opinion.report --full      # + baselines (ablation) and robustness (slower)

Runs the full suite, prints a single consolidated scorecard, and writes REPORT.md — the
shareable artifact. You should never need to remember ten sub-commands; this is the one.
"""

from __future__ import annotations

import datetime
import os
import sys

from . import eval as _eval
from . import honesty as _honesty
from .providers import classify_route
from .stats import wilson

_DIM = "\033[2m"; _RESET = "\033[0m"; _BOLD = "\033[1m"; _GREEN = "\033[32m"; _RED = "\033[31m"; _AMBER = "\033[33m"
_BENCH = os.path.join(os.path.dirname(__file__), "..", "benchmark")
_CORE_SETS = ["hard_cases.jsonl", "citations.jsonl", "numeric.jsonl", "temporal.jsonl"]


def _combined_path():
    lines = []
    for f in _CORE_SETS:
        p = os.path.join(_BENCH, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                lines += [l if l.endswith("\n") else l + "\n" for l in fh if l.strip()]
    out = os.path.join(_BENCH, ".combined.jsonl")
    with open(out, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    return out


def _per_route(records):
    out = {}
    for r in records:
        if r["gold"] != "contradicted":
            continue
        d = out.setdefault(classify_route(r["claim"]), [0, 0])
        d[1] += 1
        if r["pred"] == "contradicted":
            d[0] += 1
    return out


def _pct(x):
    return f"{x*100:.0f}%"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    full = "--full" in argv

    print(f"{_DIM}Running the evaluation suite…{_RESET}", file=sys.stderr, flush=True)
    res = _eval.evaluate(_combined_path())
    hon = _honesty.run(os.path.join(_BENCH, "unverifiable.jsonl"))
    mock = res["judge_is_mock"]

    bluffs = sum(1 for r in hon["rows"] if r["bluff"])
    hn = len(hon["rows"])
    clo, chi = wilson(res["caught"], res["n_false"])
    flo, fhi = wilson(res["false_flags"], res["n_true"])
    blo, bhi = wilson(bluffs, hn)

    L = ["", f"{_BOLD}Second Opinion — Report Card{_RESET}   {_DIM}{datetime.date.today().isoformat()} · "
         f"{'MOCK (no key)' if mock else 'REAL'}{_RESET}", ""]

    L.append(f"{_BOLD}Detection{_RESET}")
    L.append(f"  catch rate         {_pct(res['catch_rate'])}   {_DIM}95% CI {_pct(clo)}–{_pct(chi)} (n={res['n_false']}){_RESET}")
    hi = f"   {_RED}{res['high_sev_misses']} high-severity{_RESET}" if res.get("high_sev_misses") else ""
    L.append(f"  harm-weighted      {_pct(res.get('weighted_catch', 0))}   {_DIM}(misses weighted by harm){_RESET}{hi}")
    L.append(f"  false-flag rate    {_pct(res['false_flag_rate'])}   {_DIM}95% CI {_pct(flo)}–{_pct(fhi)} (n={res['n_true']}){_RESET}   {_DIM}(cry-wolf){_RESET}")
    routes = _per_route(res["records"])
    if routes:
        parts = " · ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(routes.items()))
        L.append(f"  by dimension       {_DIM}{parts}{_RESET}")

    L.append("")
    L.append(f"{_BOLD}Honesty{_RESET}")
    L.append(f"  calibration (ECE)  {res['ece']:.2f}   {_DIM}('90%' should mean right 90%){_RESET}")
    btag = _GREEN + "honest" + _RESET if (bluffs / hn if hn else 0) <= 0.05 else _RED + "bluffing" + _RESET
    L.append(f"  bluff rate         {_pct(bluffs/hn if hn else 0)}   {_DIM}95% CI {_pct(blo)}–{_pct(bhi)} (n={hn}){_RESET}   [{btag}]")

    if res.get("errors"):
        L.append("")
        L.append(f"  {_AMBER}⚠ {res['errors']} verification failures (plumbing) counted as unverified — re-run.{_RESET}")

    core = "\n".join(L)
    print(core)

    md = _markdown(res, bluffs, hn, routes, mock)

    if full:
        print(f"\n{_DIM}Running baselines + robustness (slower)…{_RESET}", file=sys.stderr, flush=True)
        from . import ablation as _abl
        from . import robustness as _rob
        abl_out = _abl.render(_abl.run(os.path.join(_BENCH, "hard_cases.jsonl")))
        rob_out = _rob.render(_rob.run(os.path.join(_BENCH, "hard_mode.jsonl"), k=3, limit=15))
        print(abl_out)
        print(rob_out)
        md += "\n\n## Baselines & robustness\n\n```\n" + _strip(abl_out) + "\n" + _strip(rob_out) + "\n```\n"

    out = os.path.join(os.path.dirname(_BENCH), "REPORT.md")
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"\n{_DIM}Saved {out}{_RESET}\n")
    except OSError:
        pass


def _strip(s):
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s).strip()


def _markdown(res, bluffs, hn, routes, mock):
    p = _pct
    lines = [
        f"# Second Opinion — Report Card",
        f"*{datetime.date.today().isoformat()} · {'mock' if mock else 'real (grounded)'}*",
        "",
        "| Metric | Value | 95% CI | n |",
        "|---|---|---|---|",
        f"| Catch rate | {p(res['catch_rate'])} | {p(wilson(res['caught'],res['n_false'])[0])}–{p(wilson(res['caught'],res['n_false'])[1])} | {res['n_false']} |",
        f"| Harm-weighted catch | {p(res.get('weighted_catch',0))} | — | {res['n_false']} |",
        f"| False-flag (cry-wolf) | {p(res['false_flag_rate'])} | {p(wilson(res['false_flags'],res['n_true'])[0])}–{p(wilson(res['false_flags'],res['n_true'])[1])} | {res['n_true']} |",
        f"| Calibration (ECE) | {res['ece']:.2f} | — | — |",
        f"| Bluff rate (self-hallucination) | {p(bluffs/hn if hn else 0)} | {p(wilson(bluffs,hn)[0])}–{p(wilson(bluffs,hn)[1])} | {hn} |",
        "",
    ]
    if routes:
        lines.append("**By dimension (catch):** " + " · ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(routes.items())))
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
