"""Token estimator — deterministic heuristic token counting.

No external tokenizer dependency. Uses ceil(character_count / 4).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def estimate_text_tokens(text: str) -> int:
    """Estimate tokens for a text string.

    Uses ceil(character_count / 4), minimum 1 for non-empty, 0 for empty.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_file_tokens(path: Path) -> int:
    """Estimate tokens for a file.

    Reads the file, counts characters, returns heuristic estimate.
    Returns 0 if file is empty or unreadable.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return estimate_text_tokens(text)
    except (OSError, UnicodeDecodeError):
        return 0


def estimate_json_tokens(obj: Any) -> int:
    """Estimate tokens for a JSON-serializable object."""
    try:
        text = json.dumps(obj, default=str, ensure_ascii=False)
        return estimate_text_tokens(text)
    except (TypeError, ValueError):
        return estimate_text_tokens(str(obj))
