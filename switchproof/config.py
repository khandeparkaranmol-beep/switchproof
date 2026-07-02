"""Dependency-free .env loader + pricing/assumption config.

Keys the engine reads:
- ANTHROPIC_API_KEY   -> enables the real frontier model (Claude).
- GROQ_API_KEY        -> enables the real open model (Llama/Qwen via Groq).
Missing either key -> that model runs in MOCK mode and the report says so. Never bluffs.

Pricing and volume are ASSUMPTIONS you should set to your real numbers — they only scale
the dollar figures, never the quality verdict. Override any of them via env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path


def load_dotenv() -> bool:
    """Load the first .env found at the repo root or cwd. Existing env vars always win."""
    for path in (Path(__file__).resolve().parent.parent / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
        return True
    return False


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Pricing:
    """USD per 1,000,000 tokens. Defaults are editable placeholders — set your real rates."""

    frontier_model: str = os.environ.get("SP_FRONTIER_MODEL", "claude-sonnet-5")
    open_model: str = os.environ.get("SP_OPEN_MODEL", "llama-3.1-8b-instant")
    frontier_in: float = _envf("SP_FRONTIER_PRICE_IN", 3.00)
    frontier_out: float = _envf("SP_FRONTIER_PRICE_OUT", 15.00)
    open_in: float = _envf("SP_OPEN_PRICE_IN", 0.05)
    open_out: float = _envf("SP_OPEN_PRICE_OUT", 0.08)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Assumptions:
    """Business inputs that scale the savings. Only affect dollars, never the quality call."""

    monthly_calls: int = int(_envf("SP_MONTHLY_CALLS", 1_000_000))

    def as_dict(self) -> dict:
        return asdict(self)
