"""Banking77 data: real customer-support queries, each labeled with one of 77 intents.

Row schema: {"text": <query>, "label": <intent>}.
- REAL: prepare() pulls Banking77 via HuggingFace `datasets` and takes an even
  (stratified) sample across all 77 intents so every routing slice is represented.
- MOCK: a bundled 12-intent fixture so the demo runs with zero downloads and zero keys.

Stratified, not random, because the per-intent routing table is the whole point — a random
draw would starve rare intents and make their slices unreadable.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

_DATA = Path(__file__).resolve().parent / "data"
MOCK_PATH = _DATA / "banking77_mock.jsonl"
DEFAULT_SAMPLE_PATH = _DATA / "banking77_sample.jsonl"


def load_jsonl(path: Path) -> List[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def labels_in(rows: List[dict]) -> List[str]:
    return sorted({r["label"] for r in rows})


def prepare(n: int = 1000, out: Path = DEFAULT_SAMPLE_PATH, seed: int = 7) -> List[dict]:
    """Stratified sample of `n` rows from Banking77's test split -> JSONL. Needs `datasets`."""
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "This step needs HuggingFace 'datasets':  pip install datasets\n"
            "(No key needed — Banking77 is a public dataset.)"
        ) from exc

    ds = load_dataset("banking77", split="test")  # 3,080 rows, 40 per intent
    names = ds.features["label"].names
    buckets: Dict[str, List[str]] = defaultdict(list)
    for row in ds:
        buckets[names[row["label"]]].append(row["text"])

    per = max(1, n // len(names))
    rng = random.Random(seed)
    sample: List[dict] = []
    for intent, texts in buckets.items():
        picks = texts if len(texts) <= per else rng.sample(texts, per)
        sample.extend({"text": t, "label": intent} for t in picks)

    if len(sample) < n:  # top up toward exactly n from the leftovers
        chosen = {(s["text"], s["label"]) for s in sample}
        leftovers = [
            {"text": t, "label": intent}
            for intent, texts in buckets.items()
            for t in texts
            if (t, intent) not in chosen
        ]
        rng.shuffle(leftovers)
        sample.extend(leftovers[: n - len(sample)])

    rng.shuffle(sample)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in sample:
            fh.write(json.dumps(r) + "\n")
    return sample


def _resolve(path: Optional[Path]) -> Path:
    if path:
        return Path(path)
    if DEFAULT_SAMPLE_PATH.is_file():
        return DEFAULT_SAMPLE_PATH
    return MOCK_PATH


def load_sample(path: Optional[Path] = None, limit: Optional[int] = None) -> List[dict]:
    """Load the sample to evaluate. Falls back to the mock fixture so the demo always runs."""
    rows = load_jsonl(_resolve(path))
    if limit:
        rows = rows[:limit]
    return rows


def source_name(path: Optional[Path] = None) -> str:
    return _resolve(path).name
