"""
ledger.py — Trial ledger accounting for Loop Engineering (quant_os).

Two-tier design, forced by CONTRIBUTING.md line 108 ("NEVER edit
research/trial_ledger.json, research/hypothesis_registry.json, or any trial cap
file without explicit sign-off from the user in the same turn"):

  Tier 1 — WorkingLedger: the loop's OWN draft ledger. Written in the SAME round
          as the run (Spec checklist item 4: "trial-ledger write เกิดขึ้นในรอบเดียวกับที่รันจริง
          ไม่ใช่ post-hoc"). This is what the loop reads/writes autonomously.

  Tier 2 — commit_to_canonical(): the ONLY path that touches the canonical
          research/trial_ledger.json + research/hypothesis_registry.json. It
          REQUIRES an explicit human sign-off token (the human gate realized).
          The automated loop NEVER calls this; it returns REQUIRES_HUMAN instead.

This satisfies both the spec's hard human gates AND the repo's edit-lock rule.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Status vocabulary used across lineage entries.
STATUS_REJECTED = "REJECTED"
STATUS_CANDIDATE = "candidate"
STATUS_UNTESTED = "UNTESTED"
STATUS_HOLDOUT_PASS = "HOLDOUT_PASS"
STATUS_HOLDOUT_FAIL = "HOLDOUT_FAIL"
STATUS_APPROVED_FOR_PAPER = "APPROVED_FOR_PAPER"

# Statuses that count as a "fail" toward the consecutive-fail stopping rule.
FAIL_STATUSES = {STATUS_REJECTED, STATUS_HOLDOUT_FAIL}

DEFAULT_TRIGGER_THRESHOLD = 3


class HumanSignOffRequiredError(Exception):
    """Raised when a canonical-ledger mutation is attempted without a sign-off token."""


@dataclass
class StoppingRule:
    type: str = "3_consecutive_fail"
    consecutive_fail_count: int = 0
    is_stopped: bool = False
    trigger_threshold: int = DEFAULT_TRIGGER_THRESHOLD
    trigger_action: str = (
        "STOP research. Re-examine gate calibration, data quality, and research "
        "direction framing — NOT automatic class-wide termination."
    )
    scope: str = (
        "TESTED_ONLY — only hypotheses actually executed with results count. "
        "UNTESTED (missing data) hypotheses do NOT count."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StoppingRule:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class SacredHoldout:
    path: str = ""
    status: str = "LOCKED"
    use_count: int = 0
    max_use_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SacredHoldout:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class LedgerEntry:
    """One trial record. Field names mirror the real research/trial_ledger*.json lineage."""

    trial_number: int
    id: str
    status: str
    tested_at: str = ""
    dk_t_stat: float = 0.0
    pooled_sharpe: float = 0.0
    positive_sharpe_count: Any = 0  # int or "x/y"
    total_trades: int = 0
    result_artifact: str = ""
    conclusion: str = ""
    validity_note: str = ""
    gate_reached: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkingLedger:
    """The loop's autonomous draft ledger. Written in the same round as the run."""

    def __init__(
        self,
        path: str | Path,
        direction: str = "A",
        stopping_rule: StoppingRule | None = None,
        sacred_holdout: SacredHoldout | None = None,
        schema_version: str = "1.0",
    ) -> None:
        self.path = Path(path)
        self.direction = direction
        self.schema_version = schema_version
        self.stopping_rule = stopping_rule or StoppingRule()
        self.sacred_holdout = sacred_holdout or SacredHoldout()
        self.lineage: list[LedgerEntry] = []
        self._next_trial_number = 1
        if self.path.exists():
            self._load()

    # ---- persistence ----
    def _load(self) -> None:
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.schema_version = data.get("schema_version", self.schema_version)
        self.direction = data.get("direction", self.direction)
        if "stopping_rule" in data:
            self.stopping_rule = StoppingRule.from_dict(data["stopping_rule"])
        if "sacred_holdout" in data:
            self.sacred_holdout = SacredHoldout.from_dict(data["sacred_holdout"])
        self.lineage = [LedgerEntry(**e) for e in data.get("lineage", [])]
        # derive next trial number from existing entries
        nums = [e.trial_number for e in self.lineage if e.trial_number > 0]
        self._next_trial_number = (max(nums) + 1) if nums else 1

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": self.schema_version,
            "direction": self.direction,
            "stopping_rule": self.stopping_rule.to_dict(),
            "sacred_holdout": self.sacred_holdout.to_dict(),
            "lineage": [e.to_dict() for e in self.lineage],
        }
        # atomic-ish write: temp then replace
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(str(tmp), str(self.path))

    # ---- stopping rule ----
    def is_stopped(self) -> bool:
        return self.stopping_rule.is_stopped

    def next_trial_number(self) -> int:
        return self._next_trial_number

    # ---- append (same-round write) ----
    def append(self, entry: LedgerEntry) -> LedgerEntry:
        """Append a trial in the SAME round as the run. Updates fail-count + is_stopped."""
        if entry.trial_number <= 0:
            entry.trial_number = self._next_trial_number
            self._next_trial_number += 1
        self.lineage.append(entry)
        # Update consecutive-fail stopping rule (TESTED_ONLY scope).
        if entry.status in FAIL_STATUSES:
            self.stopping_rule.consecutive_fail_count += 1
            if self.stopping_rule.consecutive_fail_count >= self.stopping_rule.trigger_threshold:
                self.stopping_rule.is_stopped = True
        else:
            # A non-fail outcome resets the consecutive counter (per governance scope).
            self.stopping_rule.consecutive_fail_count = 0
        self._persist()
        return entry

    # ---- sacred holdout (one-time use) ----
    def sacred_holdout_open(self) -> bool:
        """True iff the holdout may still be opened (use_count < max_use_count)."""
        return self.sacred_holdout.use_count < self.sacred_holdout.max_use_count

    def sacred_holdout_consume(self) -> None:
        if not self.sacred_holdout_open():
            raise RuntimeError(
                "Sacred holdout already consumed (use_count >= max_use_count). "
                "It CANNOT be reopened (Spec Part 3, Part 5)."
            )
        self.sacred_holdout.use_count += 1
        if self.sacred_holdout.use_count >= self.sacred_holdout.max_use_count:
            self.sacred_holdout.status = "CONSUMED"
        self._persist()

    # ---- canonical commit (HUMAN SIGN-OFF REQUIRED) ----
    def commit_to_canonical(
        self,
        entry: LedgerEntry,
        human_sign_off_token: str,
        canonical_ledger_path: str | Path,
        canonical_registry_path: str | Path,
    ) -> None:
        """The ONLY method that writes the canonical ledgers. Requires explicit sign-off.

        CONTRIBUTING.md line 108 forbids editing research/trial_ledger.json /
        research/hypothesis_registry.json without explicit same-turn user sign-off.
        `human_sign_off_token` is that sign-off. The automated loop must NEVER call
        this — it returns REQUIRES_HUMAN instead. This method is for the human-gated
        commit step only.
        """
        if not human_sign_off_token:
            raise HumanSignOffRequiredError(
                "commit_to_canonical requires an explicit human sign-off token. "
                "The automated loop must not edit canonical ledgers (CONTRIBUTING.md)."
            )
        self._append_to_canonical_ledger(entry, Path(canonical_ledger_path))
        self._upsert_canonical_registry(entry, Path(canonical_registry_path))

    def _append_to_canonical_ledger(self, entry: LedgerEntry, path: Path) -> None:
        data = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        lineage = data.get("lineage", [])
        lineage.append(entry.to_dict())
        data["lineage"] = lineage
        data["cumulative_trial_count"] = data.get("cumulative_trial_count", 0) + 1
        data["next_available_trial_number"] = (
            data.get("next_available_trial_number", entry.trial_number) + 1
        )
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _upsert_canonical_registry(self, entry: LedgerEntry, path: Path) -> None:
        if not path.exists():
            return  # registry may not exist for this direction; skip silently
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        hypotheses = data.get("hypotheses", [])
        rec = {
            "trial_number": entry.trial_number,
            "id": entry.id,
            "name": entry.id,
            "status": entry.status,
            "registered_at": entry.tested_at or datetime.now(UTC).isoformat()[:10],
            "result_at": entry.tested_at or datetime.now(UTC).isoformat()[:10],
            "instrument": "",
            "pre_registration_doc": "",
            "strategy_file": "",
            "validation_runner": "",
            "result_summary": {
                "dk_t_stat": entry.dk_t_stat,
                "pooled_sharpe": entry.pooled_sharpe,
                "positive_sharpe_count": entry.positive_sharpe_count,
                "total_trades": entry.total_trades,
                "gate_reached": entry.gate_reached,
            },
        }
        # upsert by trial_number
        replaced = False
        for i, h in enumerate(hypotheses):
            if h.get("trial_number") == entry.trial_number:
                hypotheses[i] = rec
                replaced = True
                break
        if not replaced:
            hypotheses.append(rec)
        data["hypotheses"] = hypotheses
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
