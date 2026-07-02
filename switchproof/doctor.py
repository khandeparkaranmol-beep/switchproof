"""Pre-flight check for real mode: one live call to each provider, with clear diagnosis.

Run this before a full evaluation so a bad key or wrong model id fails in 2 seconds, not
20 minutes in. It never runs the whole benchmark — just one query per model.

  python -m switchproof.doctor
"""

from __future__ import annotations

import os
import sys

from . import runners as R
from .config import Pricing, load_dotenv

_G, _A, _RED, _D, _B, _X = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"

_LABELS = ["card_arrival", "card_not_working", "declined_card_payment", "exchange_rate", "lost_or_stolen_card"]
_QUERY = "My card keeps getting declined at the shop even though I have money."
_EXPECT = "declined_card_payment"


def _check(name: str, runner: R.Runner, env_var: str) -> bool:
    label = f"{_B}{name}{_X} ({runner.model})"
    if runner.is_mock:
        print(f"  {_A}○ {label}: no {env_var} set — would run in MOCK mode.{_X}")
        print(f"    {_D}Add {env_var} to your .env to make this model real.{_X}")
        return False
    try:
        pred = runner.classify(_QUERY, _LABELS)
    except Exception as exc:  # noqa: BLE001
        print(f"  {_RED}✗ {label}: FAILED{_X}")
        print(f"    {_D}{str(exc)[:240]}{_X}")
        _hint(str(exc))
        return False
    ok = pred.label == _EXPECT
    mark = f"{_G}✓{_X}" if ok else f"{_A}✓{_X}"
    lat = f"{pred.latency_ms:.0f} ms" if pred.latency_ms else "cached"
    print(f"  {mark} {label}: replied {_B}{pred.label}{_X}  {_D}({lat}, "
          f"{pred.in_tokens} in / {pred.out_tokens} out tokens){_X}")
    if not ok:
        print(f"    {_D}Expected '{_EXPECT}' — the model works, but double-check its labels.{_X}")
    return True


def _hint(msg: str) -> None:
    m = msg.lower()
    if "401" in m or "authentication" in m or "invalid api key" in m or "invalid_api_key" in m:
        print(f"    {_D}→ The key was rejected. Check it's pasted correctly (no quotes/spaces) and not expired.{_X}")
    elif "404" in m or "not found" in m or "does not exist" in m or "decommission" in m:
        print(f"    {_D}→ That model id may be wrong/retired. Set SP_OPEN_MODEL (or SP_FRONTIER_MODEL) to a current id.{_X}")
    elif "429" in m or "rate" in m:
        print(f"    {_D}→ Rate limited. Wait a moment; the real run retries with backoff automatically.{_X}")
    elif "connection" in m or "reach" in m or "timeout" in m:
        print(f"    {_D}→ Network issue reaching the provider. Check your connection / firewall.{_X}")


def main(argv=None) -> None:
    load_dotenv()
    pricing = Pricing()
    frontier, open_ = R.make_runners(pricing.frontier_model, pricing.open_model)

    print(f"\n{_B}SwitchProof doctor{_X} — checking both providers with one live call each\n")
    print(f"  {_D}test query: \"{_QUERY}\"{_X}\n")
    ok_f = _check("frontier", frontier, "ANTHROPIC_API_KEY")
    ok_o = _check("open", open_, "GROQ_API_KEY")
    print()
    if ok_f and ok_o:
        print(f"  {_G}{_B}Both live.{_X} You're ready:  python -m switchproof --prepare 1000  &&  python -m switchproof\n")
        sys.exit(0)
    elif ok_f or ok_o:
        print(f"  {_A}One model is live, one is mock. The report will run but mark the mock side.{_X}\n")
        sys.exit(1)
    else:
        print(f"  {_A}Neither key is live — you'll get the mock demo. That's fine for a dry run:  "
              f"python -m switchproof --mock{_X}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
