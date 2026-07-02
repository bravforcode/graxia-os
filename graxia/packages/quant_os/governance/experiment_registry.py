from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import json

@dataclass(frozen=True)
class ExperimentRecord:
    """Immutable record of a research experiment. Must be registered before execution."""
    experiment_id: str
    git_commit: str
    strategy_hash: str
    parameter_hash: str
    dataset_manifest_ids: list[str]
    contract_snapshot_id: str
    execution_model_version: str
    risk_policy_version: str
    feature_set_hash: str
    random_seed: int
    trial_number: int
    trial_budget: int
    created_at_utc: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def fingerprint(self) -> str:
        data = json.dumps({
            "experiment_id": self.experiment_id,
            "strategy_hash": self.strategy_hash,
            "parameter_hash": self.parameter_hash,
            "random_seed": self.random_seed,
            "trial_number": self.trial_number,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

class ExperimentRegistry:
    """Registry for research experiments. Unregistered experiments are invalid."""

    def __init__(self):
        self._records: dict[str, ExperimentRecord] = {}

    def register(self, record: ExperimentRecord) -> tuple[bool, str]:
        if record.experiment_id in self._records:
            return False, "DUPLICATE_EXPERIMENT_ID"

        budget_exceeded = record.trial_number > record.trial_budget
        if budget_exceeded:
            return False, f"BUDGET_EXCEEDED:trial {record.trial_number}>{record.trial_budget}"

        self._records[record.experiment_id] = record
        return True, "REGISTERED"

    def get(self, experiment_id: str) -> Optional[ExperimentRecord]:
        return self._records.get(experiment_id)

    def is_registered(self, experiment_id: str) -> bool:
        return experiment_id in self._records

    def list_by_strategy(self, strategy_hash: str) -> list[ExperimentRecord]:
        return [r for r in self._records.values() if r.strategy_hash == strategy_hash]

    def count_trials(self, strategy_hash: str) -> int:
        return len(self.list_by_strategy(strategy_hash))

    def list_all(self) -> list[ExperimentRecord]:
        return list(self._records.values())

    def export_json(self) -> str:
        data = []
        for r in self._records.values():
            data.append({
                "experiment_id": r.experiment_id,
                "strategy_hash": r.strategy_hash,
                "parameter_hash": r.parameter_hash,
                "trial_number": r.trial_number,
                "trial_budget": r.trial_budget,
                "random_seed": r.random_seed,
                "created_at_utc": r.created_at_utc,
            })
        return json.dumps(data, indent=2)
