"""The terminal experience.

Design intent (working backwards from the felt experience):
- The 95% that's fine is acknowledged quietly. We do not celebrate it.
- The eye is drawn to the 1-2 things that need attention, each with its source.
- When a stage ran on mock data, we say so plainly. The tool never pretends to have
  verified something it didn't.
"""

from __future__ import annotations

import os
import sys

from .models import Label, Report
from .pipeline import Pipeline

# ANSI — soft, not loud.
_DIM = "\033[2m"
_RESET = "\033[0m"
_GREEN = "\033[32m"
_AMBER = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"

_MARK = {
    Label.SUPPORTED: f"{_GREEN}✓{_RESET}",
    Label.CONTRADICTED: f"{_RED}✗{_RESET}",
    Label.UNVERIFIED: f"{_AMBER}?{_RESET}",
    Label.NOT_CHECKABLE: f"{_DIM}·{_RESET}",
}


def _read_input(args) -> str:
    if not args:
        if not sys.stdin.isatty():
            return sys.stdin.read()
        print("Usage: python -m second_opinion <answer text | path/to/file.txt>")
        sys.exit(1)
    candidate = " ".join(args)
    if len(args) == 1 and os.path.exists(args[0]):
        with open(args[0], "r", encoding="utf-8") as fh:
            return fh.read()
    return candidate


def render(report: Report) -> str:
    lines = []
    lines.append("")
    lines.append(f"{_BOLD}Second Opinion{_RESET}")

    if report.mock_stages:
        lines.append(
            f"{_AMBER}Demo mode (no API key) — showing example results. "
            f"Run  second-opinion setup  to check real answers.{_RESET}"
        )
    lines.append("")

    # Triage gate: nothing factual to check -> stay calm and say so. Do not
    # manufacture an empty scorecard, and do not pretend to grade the opinion.
    if report.is_nothing_to_verify:
        lines.append(f"  {_DIM}Nothing to verify here — this reads as opinion or advice,{_RESET}")
        lines.append(f"  {_DIM}not factual claims. Second Opinion checks facts; it leaves judgment to you.{_RESET}")
        if report.verdicts:
            lines.append("")
            for v in report.verdicts:
                lines.append(f"  {_MARK[v.label]} {_DIM}{v.claim.text}{_RESET}")
        lines.append("")
        return "\n".join(lines)

    # Quiet pass: everything we checked, in order, marked softly.
    for v in report.verdicts:
        mark = _MARK[v.label]
        text = v.claim.text
        if v.label == Label.SUPPORTED:
            lines.append(f"  {mark} {_DIM}{text}{_RESET}")
        elif v.label == Label.NOT_CHECKABLE:
            lines.append(f"  {mark} {_DIM}{text}  (judgment, not checked){_RESET}")
        else:
            lines.append(f"  {mark} {text}")

    # Attention pass: draw the eye to what matters, with the source.
    if report.flagged:
        lines.append("")
        lines.append(f"{_BOLD}Needs your eyes{_RESET}")
        for v in report.flagged:
            color = _RED if v.label == Label.CONTRADICTED else _AMBER
            lines.append("")
            lines.append(f"  {color}{v.label.value.upper()}{_RESET}  ({int(v.confidence*100)}% confident)")
            lines.append(f"  {v.claim.text}")
            lines.append(f"  {_DIM}{v.rationale}{_RESET}")
            src = v.primary_source
            if src:
                lines.append(f"  {_DIM}↳ {src.source_title} — {src.source_url}{_RESET}")
            else:
                lines.append(f"  {_DIM}↳ no source found — that's why it's flagged, not asserted{_RESET}")

    lines.append("")
    lines.append(f"{_BOLD}{report.summary_line()}{_RESET}")
    lines.append("")
    return "\n".join(lines)


# A built-in demo answer that catches four kinds of mistake — and works with NO key,
# because the mock judge knows these facts and the math is checked deterministically.
_DEMO = ("The Eiffel Tower is 450 metres tall. 15% of 2.3 million is 3.45 million. "
         "The Great Wall of China is visible from the Moon with the naked eye. Also, "
         "vaccines cause autism. Honestly, it's the most beautiful city on earth.")


def run_demo() -> None:
    print(render(Pipeline().run(_DEMO)))


def welcome() -> None:
    print(f"\n{_BOLD}Second Opinion{_RESET} — checks what an AI told you, so you know what to trust.\n")
    print("Here it is catching four different kinds of mistake in one AI answer:")
    run_demo()
    print(f"{_DIM}(That was a built-in demo — no setup needed.){_RESET}\n")
    print("To check YOUR OWN AI answers for real (with live sources):")
    print(f"   1. one-time setup:   {_BOLD}second-opinion setup{_RESET}")
    print(f"   2. then just run:    {_BOLD}second-opinion \"paste any AI answer\"{_RESET}")
    print(f"   prefer a window?     {_BOLD}second-opinion-web{_RESET}\n")


def _write_env_key(key: str) -> None:
    path = ".env"
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    out, found = [], False
    for line in lines:
        if line.strip().startswith("ANTHROPIC_API_KEY="):
            out.append(f"ANTHROPIC_API_KEY={key}"); found = True
        else:
            out.append(line)
    if not found:
        out.insert(0, f"ANTHROPIC_API_KEY={key}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def setup_wizard() -> None:
    print(f"\n{_BOLD}Let's set up real verification.{_RESET}\n")
    print("Second Opinion needs a key to ask Claude to check facts against live sources.")
    print("Think of it like a password for the AI. It's yours, it stays on this computer,")
    print("and it costs roughly a cent or two per answer you check.\n")
    print(f"1. Get a key here:  {_BOLD}https://console.anthropic.com/settings/keys{_RESET}")
    print("2. Copy it (it starts with 'sk-ant-'), then paste it below.\n")
    try:
        key = input("Paste your key (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        print(f"\nNo problem — the demo still works: {_BOLD}second-opinion demo{_RESET}\n")
        return
    if not key.startswith("sk-"):
        print("\nThat doesn't look like an Anthropic key (it should start with 'sk-ant-'). Not saved.\n")
        return
    _write_env_key(key)
    print(f"\n{_GREEN}Saved{_RESET} to a .env file here. Checking it works…")
    os.environ["ANTHROPIC_API_KEY"] = key
    try:
        from .models import Claim
        from .providers import Judge
        label, _c, _w, _e = Judge().check(Claim(text="The Eiffel Tower is 450 metres tall."))
        if label.value == "contradicted":
            print(f"{_GREEN}✓ Working!{_RESET} Real verification is on.\n")
        else:
            print(f"Connected (got '{label.value}'). Real mode is on.\n")
    except Exception as exc:  # noqa: BLE001
        print(f"Saved your key, but the test check couldn't complete ({exc}).")
        print("Your key is stored; try:  second-opinion \"paste any AI answer\"\n")
        return
    print(f"Now try:  {_BOLD}second-opinion \"paste any AI answer here\"{_RESET}\n")


def main(argv=None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "setup":
        setup_wizard(); return
    if argv and argv[0] == "demo":
        run_demo(); return
    if not argv and sys.stdin.isatty():   # bare `second-opinion` -> friendly welcome + demo
        welcome(); return
    report = Pipeline().run(_read_input(argv))
    print(render(report))


if __name__ == "__main__":
    main()
