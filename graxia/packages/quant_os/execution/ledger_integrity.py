"""Phase 3.1A — Ledger integrity: append-only hash chain.

record_hash = SHA256(canonical_json(record) + previous_hash)
run_seal = SHA256(run_manifest_hash + final_record_hash + summary_hash)
"""
import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization."""
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class LedgerRecord:
    trade_id: str
    order_id: str
    symbol: str
    side: str
    entry_price: str
    exit_price: str
    volume: str
    pnl: str
    fees: str
    spread_cost: str
    slippage_cost: str
    entry_time: str
    exit_time: str
    close_reason: str
    strategy_id: str
    contract_snapshot_id: str
    risk_policy_version: str
    dataset_manifest_id: str
    cost_scenario: str
    git_commit: str
    record_hash: str = ""
    previous_hash: str = ""


class IntegrityChain:
    """Append-only chain with hash verification."""

    def __init__(self):
        self._records: list[LedgerRecord] = []
        self._previous_hash: str = "GENESIS"

    def append(self, record: LedgerRecord) -> LedgerRecord:
        """Append record with hash chain."""
        object.__setattr__(record, "previous_hash", self._previous_hash)
        data_for_hash = _canonical_json({
            k: v for k, v in asdict(record).items() if k != "record_hash"
        })
        record_hash = _sha256(data_for_hash + self._previous_hash)
        object.__setattr__(record, "record_hash", record_hash)
        self._previous_hash = record_hash
        self._records.append(record)
        return record

    def verify(self) -> tuple[bool, list[str]]:
        """Verify chain integrity. Returns (valid, errors)."""
        errors = []
        prev = "GENESIS"
        for i, rec in enumerate(self._records):
            if rec.previous_hash != prev:
                errors.append(
                    f"Record {i}: previous_hash mismatch "
                    f"(expected {prev}, got {rec.previous_hash})"
                )
            data_for_hash = _canonical_json({
                k: v for k, v in asdict(rec).items() if k != "record_hash"
            })
            expected_hash = _sha256(data_for_hash + rec.previous_hash)
            if rec.record_hash != expected_hash:
                errors.append(
                    f"Record {i}: hash mismatch "
                    f"(expected {expected_hash}, got {rec.record_hash})"
                )
            prev = rec.record_hash
        return len(errors) == 0, errors

    def compute_run_seal(self, run_manifest_hash: str) -> str:
        """Compute run seal: SHA256(manifest + final_hash + summary)."""
        if not self._records:
            return _sha256(run_manifest_hash + "EMPTY" + "EMPTY")
        final_hash = self._records[-1].record_hash
        summary = _canonical_json({
            "total_trades": len(self._records),
            "total_pnl": sum(float(r.pnl) for r in self._records),
        })
        return _sha256(run_manifest_hash + final_hash + summary)

    def export_jsonl(self) -> str:
        """Export chain as JSONL."""
        return "\n".join(
            _canonical_json(asdict(rec)) for rec in self._records
        )

    def detect_tamper(self, record_index: int, field: str, new_value: str) -> list[str]:
        """Detect tamper on a specific record field."""
        rec = self._records[record_index]
        object.__setattr__(rec, field, new_value)
        valid, errors = self.verify()
        return errors
