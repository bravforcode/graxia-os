"""Source of truth for Direction I DSR n_trials (spec §3, A6).

N_I = 1050 (project baseline) + |distinct screening configs| + |trials|.
Distinct = unique ``hash`` field (sha256 of mechanism|symbol|timeframe|params|data_range).
VOID configs still count (they were tried). Direction H configs/trials NEVER enter N_I.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from validation.n_trials import get_reconciled_n_trials

logger = logging.getLogger(__name__)

_DEFAULT_SCREENING_LOG = Path(__file__).resolve().parent.parent / "research" / "screening_log_i.json"
_DEFAULT_TRIAL_LEDGER = Path(__file__).resolve().parent.parent / "research" / "trial_ledger_i.json"


def count_distinct_configs(log_data: dict) -> int:
    """Count configs with distinct ``hash`` values (A6 dedup rule)."""
    seen: set[str] = set()
    for cfg in log_data.get("configs", []):
        h = cfg.get("hash")
        if h:
            seen.add(h)
    return len(seen)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Unreadable JSON at %s — treating as empty", path)
        return {}


def get_n_i(
    screening_log_path: Path | str | None = None,
    trial_ledger_path: Path | str | None = None,
    baseline: int | None = None,
) -> int:
    """Return N_I for DSR multiple-testing correction.

    baseline defaults to the project reconciled N (1050 via
    ``validation.n_trials.get_reconciled_n_trials``).
    """
    n = baseline if baseline is not None else get_reconciled_n_trials()
    screening = _read_json(Path(screening_log_path) if screening_log_path else _DEFAULT_SCREENING_LOG)
    ledger = _read_json(Path(trial_ledger_path) if trial_ledger_path else _DEFAULT_TRIAL_LEDGER)
    n += count_distinct_configs(screening)
    n += int(ledger.get("cumulative_trial_count", 0))
    return n
