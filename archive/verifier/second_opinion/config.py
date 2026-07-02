"""Tiny, dependency-free .env loader.

Reads a `.env` file from the project root (or current directory) and populates the
environment, so the API key lives in one obvious place instead of a shell export.
Existing real environment variables always win over the file (setdefault), so CI and
explicit `export`s are never overridden.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv() -> bool:
    """Load the first .env found at the project root or cwd. Returns True if one loaded."""
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",  # project root
        Path.cwd() / ".env",
    ]
    for path in candidates:
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
