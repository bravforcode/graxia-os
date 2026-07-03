import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class LockedInputs:
    """Immutable locked inputs for strategy revalidation. Must never change during validation."""

    strategy_source_hash: str
    strategy_param_hash: str
    dataset_manifest_hash: str
    timeframe_alignment_hash: str
    execution_model_version: str
    contract_snapshot_version: str
    risk_policy_version: str
    event_filter_version: str
    random_seed: int
    locked_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def master_hash(self) -> str:
        """SHA-256 of all locked input hashes combined."""
        data = json.dumps(
            {
                "strategy_source": self.strategy_source_hash,
                "strategy_param": self.strategy_param_hash,
                "dataset_manifest": self.dataset_manifest_hash,
                "timeframe_alignment": self.timeframe_alignment_hash,
                "execution_model": self.execution_model_version,
                "contract_snapshot": self.contract_snapshot_version,
                "risk_policy": self.risk_policy_version,
                "event_filter": self.event_filter_version,
                "random_seed": self.random_seed,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def verify(self, other: "LockedInputs") -> tuple[bool, list[str]]:
        """Verify all locked inputs match. Returns (match, list of mismatches)."""
        mismatches = []
        if self.strategy_source_hash != other.strategy_source_hash:
            mismatches.append("strategy_source_hash")
        if self.strategy_param_hash != other.strategy_param_hash:
            mismatches.append("strategy_param_hash")
        if self.dataset_manifest_hash != other.dataset_manifest_hash:
            mismatches.append("dataset_manifest_hash")
        if self.timeframe_alignment_hash != other.timeframe_alignment_hash:
            mismatches.append("timeframe_alignment_hash")
        if self.execution_model_version != other.execution_model_version:
            mismatches.append("execution_model_version")
        if self.contract_snapshot_version != other.contract_snapshot_version:
            mismatches.append("contract_snapshot_version")
        if self.risk_policy_version != other.risk_policy_version:
            mismatches.append("risk_policy_version")
        if self.event_filter_version != other.event_filter_version:
            mismatches.append("event_filter_version")
        if self.random_seed != other.random_seed:
            mismatches.append("random_seed")
        return len(mismatches) == 0, mismatches
