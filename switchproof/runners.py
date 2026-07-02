"""The two model runners that classify a query into one of the 77 Banking77 intents.

- FrontierRunner  -> Claude (Anthropic), the incumbent / reference model.
- OpenRunner      -> an open-weight model (Llama/Qwen) via Groq's OpenAI-compatible API,
                     called with stdlib urllib so the engine adds no new dependencies.

Each returns a Prediction(label, in_tokens, out_tokens, latency_ms). Real predictions are
cached by (model, query). If a provider key is missing, that model runs in MOCK mode and
records it, so the report can say plainly which numbers are real. The engine never bluffs.

MOCK mode is designed to look like a real result: the frontier model is near-perfect, the
open model is strong overall but reliably weaker on a few confusable intents — so the
per-intent routing story ("switch most, keep these on frontier") emerges honestly.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .cache import cache_key, get_cache

# Proactive throttle for the open model — Groq's free tier is token-bound (TPM ~6K for
# llama-3.1-8b-instant), so pacing under the limit is faster overall than hammering into
# 429s. Default ~10 req/min keeps a ~500-token classification call under 6K TPM. Bump via
# SP_OPEN_RPM when you have a higher-limit plan.
_last_open_call = [0.0]
_open_lock = threading.Lock()


def _throttle_open() -> None:
    try:
        rpm = float(os.environ.get("SP_OPEN_RPM", 10))
    except ValueError:
        rpm = 10.0
    if rpm <= 0:
        return
    interval = 60.0 / rpm
    with _open_lock:
        wait = _last_open_call[0] + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_open_call[0] = time.monotonic()


@dataclass
class Prediction:
    label: str
    in_tokens: int
    out_tokens: int
    latency_ms: float
    mock: bool = False


def _est_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def build_prompt(query: str, labels: List[str]) -> Tuple[str, str]:
    """A single classification prompt shared by both models, so cost differences come from
    price-per-token, not prompt size. Returns (system, user)."""
    system = (
        "You are an intent classifier for a mobile bank's customer support. "
        "Read the customer's message and reply with EXACTLY ONE intent label from the "
        "provided list — just the label, no punctuation, no explanation."
    )
    user = "INTENT LABELS:\n" + "\n".join(labels) + f"\n\nCUSTOMER MESSAGE:\n{query}\n\nLABEL:"
    return system, user


def _coerce_label(raw: str, labels: List[str]) -> str:
    """Map a model's free-text reply to the closest allowed label (exact -> substring)."""
    t = (raw or "").strip().strip(".\"'` ").lower()
    lut = {l.lower(): l for l in labels}
    if t in lut:
        return lut[t]
    for l in labels:  # the model sometimes adds words around the label
        if l.lower() in t or t in l.lower():
            return l
    return "UNKNOWN"


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class Runner:
    name = "base"
    model = "base"
    is_mock = True

    def classify(self, query: str, labels: List[str]) -> Prediction:
        raise NotImplementedError

    def _cached(self, query: str, labels: List[str]) -> Prediction:
        cache = get_cache()
        key = cache_key(self.model, query)
        hit = cache.get(key)
        if hit is not None:
            return Prediction(hit["label"], hit["in"], hit["out"], hit["ms"], mock=False)
        pred = self._call(query, labels)
        cache.put(key, {"label": pred.label, "in": pred.in_tokens, "out": pred.out_tokens, "ms": pred.latency_ms})
        return pred

    def _call(self, query: str, labels: List[str]) -> Prediction:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Frontier (Anthropic / Claude)
# --------------------------------------------------------------------------- #
class FrontierRunner(Runner):
    def __init__(self, model: str) -> None:
        self.model = model
        self.name = "frontier"
        self.is_mock = not os.environ.get("ANTHROPIC_API_KEY")

    def classify(self, query: str, labels: List[str]) -> Prediction:
        if self.is_mock:
            return _mock_frontier(query, labels)
        return self._cached(query, labels)

    def _call(self, query: str, labels: List[str]) -> Prediction:  # pragma: no cover - needs key
        from anthropic import Anthropic

        system, user = build_prompt(query, labels)
        client = Anthropic()
        t0 = time.time()
        msg = client.messages.create(
            model=self.model, max_tokens=20, system=system,
            messages=[{"role": "user", "content": user}],
        )
        ms = (time.time() - t0) * 1000
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        usage = getattr(msg, "usage", None)
        it = getattr(usage, "input_tokens", None) or _est_tokens(system + user)
        ot = getattr(usage, "output_tokens", None) or _est_tokens(text)
        return Prediction(_coerce_label(text, labels), int(it), int(ot), ms)


# --------------------------------------------------------------------------- #
# Open-weight (Groq OpenAI-compatible endpoint)
# --------------------------------------------------------------------------- #
class OpenRunner(Runner):
    def __init__(self, model: str, base_url: str = "https://api.groq.com/openai/v1") -> None:
        self.model = model
        self.name = "open"
        self.base_url = os.environ.get("SP_OPEN_BASE_URL", base_url)
        self.is_mock = not os.environ.get("GROQ_API_KEY")

    def classify(self, query: str, labels: List[str]) -> Prediction:
        if self.is_mock:
            return _mock_open(query, labels)
        return self._cached(query, labels)

    def _call(self, query: str, labels: List[str]) -> Prediction:  # pragma: no cover - needs key
        system, user = build_prompt(query, labels)
        payload = json.dumps({
            "model": self.model,
            "temperature": 0,
            "max_tokens": 20,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode("utf-8")
        _throttle_open()  # pace under the free-tier token/minute limit before firing
        t0 = time.time()
        body = self._post_with_retry(payload)
        ms = (time.time() - t0) * 1000
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        it = usage.get("prompt_tokens") or _est_tokens(system + user)
        ot = usage.get("completion_tokens") or _est_tokens(text)
        return Prediction(_coerce_label(text, labels), int(it), int(ot), ms)

    def _post_with_retry(self, payload: bytes, tries: int = 5) -> dict:  # pragma: no cover - needs key
        """POST to the OpenAI-compatible endpoint with backoff on 429/5xx — so a long run
        survives Groq free-tier rate limits instead of dying halfway."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "switchproof/0.1",  # Groq/Cloudflare blocks urllib's default UA (403/1010)
        }
        last = None
        for attempt in range(tries):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code in (429, 500, 502, 503, 529) and attempt < tries - 1:
                    retry_after = exc.headers.get("retry-after")
                    wait = float(retry_after) if retry_after else min(2 ** attempt, 30)
                    time.sleep(wait)
                    continue
                detail = exc.read().decode("utf-8")[:200]
                raise RuntimeError(f"Open model API error {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                last = exc
                if attempt < tries - 1:
                    time.sleep(min(2 ** attempt, 10)); continue
                raise RuntimeError(f"Could not reach the open-model API: {exc.reason}") from exc
        raise RuntimeError(f"Open model API failed after {tries} attempts: {last}")


# --------------------------------------------------------------------------- #
# Mock behavior — deterministic, realistic
# --------------------------------------------------------------------------- #
def _unit(seed: str) -> float:
    """Deterministic pseudo-random in [0,1) from a string (stable across runs)."""
    h = 0
    for ch in seed:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return (h % 100000) / 100000.0


# Intents the small open model reliably confuses (target, probability). Mirrors the real
# Banking77 pain points where similar-sounding intents blur together.
_CONFUSABLE = {
    "card_not_working": ("declined_card_payment", 0.45),
    "declined_card_payment": ("card_not_working", 0.22),
    "pending_transfer": ("transfer_not_received_by_recipient", 0.42),
    "transfer_not_received_by_recipient": ("pending_transfer", 0.28),
    "balance_not_updated_after_bank_transfer": ("pending_transfer", 0.20),
}


def _mock_frontier(query: str, labels: List[str]) -> Prediction:
    system, user = build_prompt(query, labels)
    gold = _gold_hint(query, labels)
    r = _unit("F::" + query)
    label = gold
    if r > 0.975 and len(labels) > 1:  # ~2.5% frontier error
        label = labels[int(_unit("FE::" + query) * len(labels)) % len(labels)]
    return Prediction(label, _est_tokens(system + user), 4, 0.0, mock=True)


def _mock_open(query: str, labels: List[str]) -> Prediction:
    system, user = build_prompt(query, labels)
    gold = _gold_hint(query, labels)
    r = _unit("O::" + query)
    label = gold
    if gold in _CONFUSABLE:
        target, prob = _CONFUSABLE[gold]
        if r < prob and target in labels:
            label = target
    if label == gold and _unit("OG::" + query) > 0.93 and len(labels) > 1:  # ~7% generic slips
        label = labels[int(_unit("OE::" + query) * len(labels)) % len(labels)]
    return Prediction(label, _est_tokens(system + user), 4, 0.0, mock=True)


# In mock mode we know the gold label because the fixture carries it; the evaluator passes
# it through a thread-local so runners can simulate realistic behavior without an API.
_GOLD_CTX: dict = {}


def set_gold_context(mapping: dict) -> None:
    _GOLD_CTX.clear()
    _GOLD_CTX.update(mapping)


def _gold_hint(query: str, labels: List[str]) -> str:
    g = _GOLD_CTX.get(query)
    if g in labels:
        return g
    return labels[int(_unit("G::" + query) * len(labels)) % len(labels)]


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def make_runners(frontier_model: str, open_model: str) -> Tuple[FrontierRunner, OpenRunner]:
    return FrontierRunner(frontier_model), OpenRunner(open_model)
