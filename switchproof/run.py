"""Orchestrator + CLI. Runs the switch evaluation and writes:
  - web/public/report.json   (the React app reads this)
  - SWITCH_REPORT.md         (a shareable text summary)
and prints a compact scorecard to the terminal.

Usage:
  python -m switchproof                     # mock mode, uses the bundled fixture
  python -m switchproof --prepare 1000      # download + stratify a real 1,000-row sample
  python -m switchproof --limit 2000        # evaluate more rows (cache makes re-runs cheap)
  python -m switchproof --monthly-calls 5000000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import data as D
from . import evaluate as E
from . import runners as R
from .config import Assumptions, Pricing, load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
_REPORT_JSON = _ROOT / "web" / "public" / "report.json"
_REPORT_MD = _ROOT / "SWITCH_REPORT.md"

_C = {"g": "\033[32m", "a": "\033[33m", "r": "\033[31m", "d": "\033[2m", "b": "\033[1m", "x": "\033[0m"}
_VERDICT_TEXT = {
    "SAFE_ALL": ("g", "SAFE TO SWITCH", "The open model matches the frontier model across the board."),
    "SAFE_HYBRID": ("g", "SAFE TO SWITCH (hybrid)", "Switch the safe slices to open; keep a few on frontier."),
    "NOT_YET": ("a", "NOT YET", "The open model drifts on too much traffic — fine-tune or wait."),
}


def _money(x: float) -> str:
    if abs(x) >= 1000:
        return f"${x:,.0f}"
    return f"${x:,.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _print_card(rep: dict) -> None:
    h = rep["headline"]
    color, title, sub = _VERDICT_TEXT.get(h["verdict"], ("a", h["verdict"], ""))
    ag = h["agreement"]
    print()
    print(f"{_C['b']}SwitchProof — {rep['task']['name']}{_C['x']}")
    if rep["mode"] == "mock":
        print(f"{_C['a']}Demo mode (mock models: {', '.join(rep['mock_models'])}) — "
              f"add API keys for real numbers.{_C['x']}")
    print(f"{_C['d']}{rep['task']['n']} queries · {rep['task']['n_intents']} intents · "
          f"{rep['models']['frontier']['name']}  →  {rep['models']['open']['name']}{_C['x']}")
    print()
    print(f"  {_C[color]}{_C['b']}{title}{_C['x']}   {_C['d']}{sub}{_C['x']}")
    print()
    print(f"  Agreement with frontier : {_C['b']}{_pct(ag['rate'])}{_C['x']}  "
          f"{_C['d']}(95% CI {_pct(ag['low'])}–{_pct(ag['high'])}){_C['x']}")
    print(f"  Quality after routing   : {_C['b']}{_pct(h['quality_after_routing'])}{_C['x']}")
    print(f"  Traffic switchable      : {_C['b']}{_pct(h['traffic_switchable_pct'])}{_C['x']}")
    print()
    print(f"  Monthly savings         : {_C['g']}{_C['b']}{_money(h['monthly_savings'])}{_C['x']}"
          f"  {_C['d']}({_pct(h['savings_pct'])} of today's spend · {_money(h['annual_savings'])}/yr){_C['x']}")
    print(f"  {_C['d']}today {_money(rep['cost']['monthly_frontier'])}/mo · "
          f"all-open {_money(rep['cost']['monthly_open'])}/mo · "
          f"hybrid {_money(rep['cost']['monthly_hybrid'])}/mo "
          f"@ {rep['assumptions']['monthly_calls']:,} calls{_C['x']}")
    if rep["routing"]["weak_intents"]:
        print()
        print(f"  {_C['a']}Keep on frontier:{_C['x']} {', '.join(rep['routing']['weak_intents'])}")
    print()
    print(f"  {_C['d']}Wrote {_REPORT_JSON.relative_to(_ROOT)} and {_REPORT_MD.name}. "
          f"Run the app:  cd web && npm install && npm run dev{_C['x']}")
    print()


def _write_md(rep: dict) -> None:
    h = rep["headline"]; ag = h["agreement"]
    _, title, sub = _VERDICT_TEXT.get(h["verdict"], ("", h["verdict"], ""))
    lines = [
        f"# SwitchProof report — {rep['task']['name']}", "",
        f"_{rep['generated_at']} · {rep['mode'].upper()} mode_"
        + (f" · mock: {', '.join(rep['mock_models'])}" if rep["mock_models"] else ""), "",
        f"**Verdict: {title}.** {sub}", "",
        f"- **Agreement with frontier:** {_pct(ag['rate'])} (95% CI {_pct(ag['low'])}–{_pct(ag['high'])})",
        f"- **Quality after routing:** {_pct(h['quality_after_routing'])}",
        f"- **Traffic switchable to open:** {_pct(h['traffic_switchable_pct'])}",
        f"- **Monthly savings:** {_money(h['monthly_savings'])} "
        f"({_pct(h['savings_pct'])} of today's spend, {_money(h['annual_savings'])}/yr) "
        f"at {rep['assumptions']['monthly_calls']:,} calls/mo",
        f"- **Models:** {rep['models']['frontier']['name']} → {rep['models']['open']['name']}", "",
        "## Cost scenarios (per month)", "",
        f"| Scenario | Monthly cost |", "|---|---|",
        f"| Today (all frontier) | {_money(rep['cost']['monthly_frontier'])} |",
        f"| Naive switch (all open) | {_money(rep['cost']['monthly_open'])} |",
        f"| Hybrid (route safe slices) | {_money(rep['cost']['monthly_hybrid'])} |", "",
        "## Intents to keep on frontier", "",
        ("- " + "\n- ".join(rep["routing"]["weak_intents"])) if rep["routing"]["weak_intents"]
        else "_None — every slice is safe to switch._", "",
        "## Per-intent agreement (worst first)", "",
        "| Intent | n | Agreement | Action |", "|---|---|---|---|",
    ]
    for it in rep["intents"]:
        lines.append(f"| {it['intent']} | {it['n']} | {_pct(it['agreement'])} | "
                     f"{'keep on frontier' if it['action']=='keep_on_frontier' else 'switch'} |")
    lines += ["", "---", "_Pricing and volume are assumptions you set; they scale the dollars, "
              "not the quality verdict. Agreement is measured against the frontier model as the "
              "live reference (Case 1)._", ""]
    _REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="switchproof", description="Prove a model switch is safe + priced.")
    ap.add_argument("--prepare", type=int, metavar="N", help="download + stratify N real Banking77 rows")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N rows")
    ap.add_argument("--monthly-calls", type=int, default=None, help="override monthly call volume")
    ap.add_argument("--mock", action="store_true", help="force both models to mock (offline, free, deterministic)")
    args = ap.parse_args(argv)

    if args.prepare:
        print(f"Preparing a stratified {args.prepare}-row Banking77 sample …")
        D.prepare(args.prepare)
        print(f"Wrote {D.DEFAULT_SAMPLE_PATH.name}. Now run:  python -m switchproof")
        return

    pricing = Pricing()
    assumptions = Assumptions()
    if args.monthly_calls:
        assumptions.monthly_calls = args.monthly_calls

    sample = D.load_sample(limit=args.limit)
    frontier, open_ = R.make_runners(pricing.frontier_model, pricing.open_model)
    if args.mock:
        frontier.is_mock = open_.is_mock = True

    def progress(done, total):
        print(f"  … {done}/{total}", file=sys.stderr)

    rep = E.run(sample, frontier, open_, pricing, assumptions, progress=progress)

    _REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_JSON.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    _write_md(rep)
    _print_card(rep)


if __name__ == "__main__":
    main()
