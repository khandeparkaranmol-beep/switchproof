"""Model-Switch Report — prove whether a task can move from a frontier model to a
cheaper open model without regressing, and put a dollar figure on the savings.

The story (Case 1 — you already run a frontier model):
    The frontier model's output is your FREE reference. Run the cheap open model on the
    same inputs, measure how often it agrees, find the slices where it doesn't, route
    only those back to frontier, and report the dollars saved.

Reuses the wider package's spine: the Anthropic client pattern, the durable JSONL cache,
Wilson intervals from ``stats``, and the ``.env`` loader. Runs fully in MOCK mode with no
keys so the whole experience is demoable before wiring a real open-model provider.
"""

from __future__ import annotations

__all__ = ["data", "runners", "evaluate", "report"]
