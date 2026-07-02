"""SwitchProof — prove you can move a task from a frontier model to a cheaper open
model without losing quality, and put a dollar figure on the savings.

Case 1 (you already run a frontier model): the frontier model's own output is your free
reference. Run the cheap open model on the same real inputs, measure agreement, find the
slices where it drifts, route only those back to frontier, and report the money saved.

Self-contained: vendors its own tiny stats / dotenv / cache helpers, so it stands alone.
Runs fully in MOCK mode with no API keys, so the whole product is demoable instantly.
"""

from __future__ import annotations

__version__ = "0.1.0"
