"""A durable verdict cache — so slow, paid verification is never redone or lost.

Every real (grounded) verdict is keyed by (model, claim text) and appended to a JSONL file
the moment it's produced. Consequences:
- An interrupted eval/answereval/fit run loses nothing — re-running skips cached claims.
- Re-runs are near-instant and free (no repeated web searches).
- Results are reproducible for a fixed benchmark.

To force fresh verification, delete benchmark/.verdict_cache.jsonl (or set SECOND_OPINION_NO_CACHE=1).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import List, Optional

from .models import Evidence, Label

def _default_cache_path() -> Path:
    """Repo benchmark dir in dev; a home directory when pip-installed; env override always wins."""
    env = os.environ.get("SECOND_OPINION_CACHE")
    if env:
        return Path(env)
    repo_bench = Path(__file__).resolve().parent.parent / "benchmark"
    if repo_bench.is_dir():  # running from a clone
        return repo_bench / ".verdict_cache.jsonl"
    return Path.home() / ".second-opinion" / "verdict_cache.jsonl"  # installed


_CACHE_PATH = _default_cache_path()


def cache_key(model: str, claim_text: str) -> str:
    return hashlib.sha1(f"{model}::{claim_text.strip()}".encode("utf-8")).hexdigest()


def serialize(label: Label, conf: float, rationale: str, evidence: List[Evidence]) -> dict:
    return {
        "label": label.value,
        "confidence": conf,
        "rationale": rationale,
        "evidence": [
            {"snippet": e.snippet, "source_title": e.source_title,
             "source_url": e.source_url, "supports": e.supports}
            for e in evidence
        ],
    }


def deserialize(d: dict):
    label = Label(d["label"])
    evidence = [
        Evidence(snippet=e.get("snippet", ""), source_title=e.get("source_title", ""),
                 source_url=e.get("source_url", ""), supports=e.get("supports"))
        for e in d.get("evidence", [])
    ]
    return label, float(d.get("confidence", 0.4)), d.get("rationale", ""), evidence


class VerdictCache:
    def __init__(self, path: Path = _CACHE_PATH) -> None:
        self.path = Path(path)
        self.enabled = os.environ.get("SECOND_OPINION_NO_CACHE") != "1"
        self.mem: dict = {}
        if self.enabled and self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    self.mem[rec["key"]] = rec["verdict"]
                except (json.JSONDecodeError, KeyError):
                    continue

    def get(self, key: str) -> Optional[dict]:
        return self.mem.get(key) if self.enabled else None

    def put(self, key: str, verdict: dict) -> None:
        if not self.enabled:
            return
        self.mem[key] = verdict
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:  # append = durable mid-run
            fh.write(json.dumps({"key": key, "verdict": verdict}) + "\n")


_CACHE: Optional[VerdictCache] = None


def get_cache() -> VerdictCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = VerdictCache()
    return _CACHE
