"""Banking77 data: a stratified sample of real customer-support queries, each labeled
with one of 77 banking intents.

Two paths, same row schema ``{"text": ..., "label": ...}``:
- REAL: ``prepare()`` pulls Banking77 via HuggingFace ``datasets`` and takes an even
  (stratified) sample across all 77 intents, so every slice is represented.
- MOCK: a small bundled fixture (``benchmark/banking77_mock.jsonl``, 12 intents) so the
  whole demo runs with zero downloads and zero keys.

Why stratified, not random: the per-intent routing table is the point. A random 1,000
would starve rare intents; even sampling gives each intent a fair, comparable slice.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

_BENCH = Path(__file__).resolve().parent.parent.parent / "benchmark"
MOCK_PATH = _BENCH / "banking77_mock.jsonl"
DEFAULT_SAMPLE_PATH = _BENCH / "banking77_sample.jsonl"


def load_jsonl(path: Path) -> List[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def labels_in(rows: List[dict]) -> List[str]:
    """The sorted set of intent labels present in a sample (the allowed answer set)."""
    return sorted({r["label"] for r in rows})


def by_label(rows: List[dict]) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        buckets[r["label"]].append(r)
    return buckets


def prepare(n: int = 1000, out: Path = DEFAULT_SAMPLE_PATH, seed: int = 7) -> List[dict]:
    """Build a stratified sample of `n` rows from Banking77's test split and write JSONL.

    Requires ``datasets`` (``pip install datasets``). Uses the test split (3,080 rows,
    40 per intent) so we never sample the examples a fine-tune might have trained on.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "This step needs HuggingFace 'datasets'.  pip install datasets\n"
            "(No key needed — it's a public dataset.)"
        ) from exc

    ds = load_dataset("banking77", split="test")
    names = ds.features["label"].names  # 77 intent strings
    buckets: Dict[str, List[str]] = defaultdict(list)
    for row in ds:
        buckets[names[row["label"]]].append(row["text"])

    per = max(1, n // len(names))
    rng = random.Random(seed)
    sample: List[dict] = []
    for intent, texts in buckets.items():
        picks = texts if len(texts) <= per else rng.sample(texts, per)
        sample.extend({"text": t, "label": intent} for t in picks)

    # Top up toward exactly n with a random draw from the leftovers, so a request for
    # 1000 lands near 1000 rather than 77*13=1001-ish (even split is close but not exact).
    if len(sample) < n:
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


def load_sample(path: Optional[Path] = None, limit: Optional[int] = None) -> List[dict]:
    """Load the sample to evaluate on. Falls back to the mock fixture when no real sample
    has been prepared yet, so the demo always runs."""
    p = Path(path) if path else (DEFAULT_SAMPLE_PATH if DEFAULT_SAMPLE_PATH.is_file() else MOCK_PATH)
    if not p.is_file():
        p = MOCK_PATH
    rows = load_jsonl(p)
    if limit:
        rows = rows[:limit]
    return rows


def source_name(path: Optional[Path] = None) -> str:
    p = Path(path) if path else (DEFAULT_SAMPLE_PATH if DEFAULT_SAMPLE_PATH.is_file() else MOCK_PATH)
    if not p.is_file():
        p = MOCK_PATH
    return p.name
