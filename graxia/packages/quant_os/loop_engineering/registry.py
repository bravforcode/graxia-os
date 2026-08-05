"""
registry.py — Hypothesis registry + provenance guards for Loop Engineering.

Spec Part 2.3: before the agent proposes a NEW hypothesis it MUST query
hypothesis_registry.json + PROVENANCE_INDEX.md to prevent "zombie hypotheses"
(RYDC/CAM that were REJECTED yet resurface as "untested").

Spec Part 2.2: result artifacts must be timestamp-checked against the bug-fix
timeline in PROVENANCE_INDEX.md (pre-Jul-18 Sharpe values are inflated/invalid).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Terminal statuses that mean "do not re-propose this as untested".
TERMINAL_STATUSES = {"REJECTED", "HOLDOUT_FAIL", "RESERVED"}

# Documented bug-fix cutoff: results generated before this may be invalid.
DEFAULT_BUG_FIX_CUTOFF = "2026-07-18"


@dataclass
class ProvenanceCheck:
    status: str  # "VALID" | "INVALID_PREFIX" | "UNKNOWN"
    cutoff: str
    artifact_date: str | None
    note: str


def load_hypothesis_registry(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Hypothesis registry not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_zombie(registry: dict[str, Any], candidate_id: str) -> bool:
    """True if `candidate_id` already exists with a terminal (REJECTED) status.

    Prevents resurrecting a dead candidate as "untested" (Spec Part 2.3).
    """
    for h in registry.get("hypotheses", []):
        if h.get("id") == candidate_id and h.get("status") in TERMINAL_STATUSES:
            return True
    return False


def _parse_cutoff(provenance_path: str | Path) -> str:
    """Extract the bug-fix cutoff date from PROVENANCE_INDEX.md if present."""
    p = Path(provenance_path)
    if not p.exists():
        return DEFAULT_BUG_FIX_CUTOFF
    text = p.read_text(encoding="utf-8", errors="ignore")
    # Look for "BEFORE Jul 18" / "BEFORE 2026-07-18" style markers.
    m = re.search(r"BEFORE\s+(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    m = re.search(r"BEFORE\s+([A-Za-z]{3})\s+(\d{1,2})", text)
    if m:
        mon = m.group(1)
        day = int(m.group(2))
        months = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }
        if mon in months:
            return f"2026-{months[mon]:02d}-{day:02d}"
    return DEFAULT_BUG_FIX_CUTOFF


def _artifact_date(artifact_path: str | Path) -> str | None:
    """Best-effort date extraction from an artifact filename (YYYYMMDD or YYYY-MM-DD)."""
    name = Path(artifact_path).name
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if m:
        return m.group(0)
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def check_provenance(
    artifact_path: str | Path,
    provenance_path: str | Path,
    cutoff: str | None = None,
) -> ProvenanceCheck:
    """Verify an artifact was produced AFTER the bug-fix timeline.

    Returns INVALID_PREFIX if the artifact predates the cutoff (its Sharpe may be
    inflated). UNKNOWN if no date could be extracted (caller should treat as a warning).
    """
    cut = cutoff or _parse_cutoff(provenance_path)
    art_date = _artifact_date(artifact_path)
    if art_date is None:
        return ProvenanceCheck(
            status="UNKNOWN",
            cutoff=cut,
            artifact_date=None,
            note="No date in artifact filename; cannot verify against bug-fix timeline. Treat as unverified.",
        )
    if art_date < cut:
        return ProvenanceCheck(
            status="INVALID_PREFIX",
            cutoff=cut,
            artifact_date=art_date,
            note=f"Artifact dated {art_date} predates bug-fix cutoff {cut}; Sharpe may be inflated/invalid.",
        )
    return ProvenanceCheck(
        status="VALID",
        cutoff=cut,
        artifact_date=art_date,
        note=f"Artifact dated {art_date} is post-fix (cutoff {cut}).",
    )
