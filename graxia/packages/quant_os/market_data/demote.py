"""Cost-drift demotion (Phase 1).

When a tradeable symbol's current spread-bps distribution drifts from its
baseline (PSI > threshold, reusing the shared psi() primitive), the pipeline:
  1. flips the symbol tradeable → measuring in tradeable_universe.json,
  2. flags any open live positions via the kill switch (kill_symbol),
  3. invalidates every trial/registry entry that referenced the symbol
     (research/ledger_invalidation.py — append-only),
  4. appends an audit-log entry with the PSI value and reason.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.stats.psi import psi

COST_DRIFT_PSI_THRESHOLD: float = 0.25  # = DriftMonitor default (ml/drift_monitor.py:85)
MIN_SAMPLES: int = 5


def cost_drift_psi(baseline_samples: list[float], current_samples: list[float]) -> float:
    """PSI between two spread-bps sample distributions (normal approximation),
    identical in spirit to DriftMonitor's baseline/current window comparison."""
    b_mean = sum(baseline_samples) / len(baseline_samples)
    b_std = max(math.sqrt(sum((v - b_mean) ** 2 for v in baseline_samples) / len(baseline_samples)), 1e-10)
    c_mean = sum(current_samples) / len(current_samples)
    c_std = max(math.sqrt(sum((v - c_mean) ** 2 for v in current_samples) / len(current_samples)), 1e-10)
    return psi(baseline_mean=b_mean, baseline_std=b_std, current_mean=c_mean, current_std=c_std)


@dataclass(frozen=True)
class DemotionResult:
    symbol: str
    psi: float
    threshold: float
    previous_status: str
    audit_ref: str


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".demote_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, str(path))


class DemotionChecker:
    def __init__(
        self,
        *,
        universe_path: str | Path,
        cost_calibration_path: str | Path,
        kill_switch,
        audit_log_path: str | Path,
        ledger_invalidate=None,
        threshold: float = COST_DRIFT_PSI_THRESHOLD,
    ):
        """kill_switch: a risk.kill_switch.KillSwitch instance (real, with a
        tmp state file in tests). ledger_invalidate: research/ledger_invalidation
        .invalidate_symbol, injected for test isolation."""
        self._universe_path = Path(universe_path)
        self._cost_calibration_path = Path(cost_calibration_path)
        self._kill_switch = kill_switch
        self._audit_log_path = Path(audit_log_path)
        self._ledger_invalidate = ledger_invalidate
        self._threshold = threshold

    def _demote_in_universe(self, symbol: str) -> str:
        universe = json.loads(self._universe_path.read_text(encoding="utf-8"))
        tradeable = universe.get("tradeable", [])
        idx = next((i for i, e in enumerate(tradeable) if e.get("symbol") == symbol), None)
        if idx is None:
            raise KeyError(f"{symbol} is not tradeable — cannot demote")
        entry = tradeable.pop(idx)
        entry["demoted_at"] = datetime.now(UTC).isoformat()
        entry["demoted_reason"] = "cost_drift_psi"
        universe.setdefault("measuring", []).append(entry)
        universe.setdefault("summary", {}).update(
            {"tradeable": len(universe.get("tradeable", [])), "measuring": len(universe.get("measuring", []))}
        )
        _atomic_write_json(self._universe_path, universe)
        return "tradeable"

    def check(
        self,
        symbol: str,
        baseline_samples: list[float],
        current_samples: list[float],
    ) -> DemotionResult | None:
        """Return a DemotionResult when drift is detected, else None.
        Requires >= MIN_SAMPLES per window."""
        if len(baseline_samples) < MIN_SAMPLES or len(current_samples) < MIN_SAMPLES:
            return None
        psi_value = cost_drift_psi(baseline_samples, current_samples)
        if psi_value <= self._threshold:
            return None

        previous_status = self._demote_in_universe(symbol)
        self._kill_switch.kill_symbol(symbol, reason=f"cost_drift_psi={psi_value:.4f}", source="demote:cost_drift")
        if self._ledger_invalidate is not None:
            self._ledger_invalidate(symbol, reason=f"cost drift PSI={psi_value:.4f}", audit_ref="pending")

        audit_ref = f"demote:{symbol}:{datetime.now(UTC).isoformat()}"
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._audit_log_path, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "event": "universe.demote",
                        "symbol": symbol,
                        "reason": "cost_drift_psi",
                        "psi": round(psi_value, 6),
                        "threshold": self._threshold,
                        "previous_status": previous_status,
                        "new_status": "measuring",
                        "kill_switch_flagged": True,
                        "audit_ref": audit_ref,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    default=str,
                )
                + "\n"
            )
        return DemotionResult(
            symbol=symbol,
            psi=psi_value,
            threshold=self._threshold,
            previous_status=previous_status,
            audit_ref=audit_ref,
        )
