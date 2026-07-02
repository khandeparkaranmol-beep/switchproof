"""Durable classification cache — so a 1,000-row (×2 model) run is never redone or lost.

Every real prediction is keyed by (model, query) and appended to a JSONL file the moment
it's produced. An interrupted run resumes for free; re-runs are instant; bumping the sample
from 1,000 to 2,000 only pays for the new 1,000. Mock predictions are not cached (free).

Force a fresh run: delete switchproof/data/.pred_cache.jsonl (or set SP_NO_CACHE=1).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

_CACHE_PATH = Path(__file__).resolve().parent / "data" / ".pred_cache.jsonl"


def cache_key(model: str, text: str) -> str:
    return hashlib.sha1(f"{model}::{text.strip()}".encode("utf-8")).hexdigest()


class PredCache:
    def __init__(self, path: Path = _CACHE_PATH) -> None:
        self.path = Path(path)
        self.enabled = os.environ.get("SP_NO_CACHE") != "1"
        self.mem: dict = {}
        if self.enabled and self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    self.mem[rec["key"]] = rec["value"]
                except (json.JSONDecodeError, KeyError):
                    continue

    def get(self, key: str) -> Optional[dict]:
        return self.mem.get(key) if self.enabled else None

    def put(self, key: str, value: dict) -> None:
        if not self.enabled:
            return
        self.mem[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "value": value}) + "\n")


_CACHE: Optional[PredCache] = None


def get_cache() -> PredCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = PredCache()
    return _CACHE
