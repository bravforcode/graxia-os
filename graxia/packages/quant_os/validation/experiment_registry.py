"""Phase 5 — Experiment registry. Every experiment must be registered before running."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_REGISTRY_PATH = Path(__file__).parent / ".experiment_registry.json"


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    git_commit: str
    strategy_snapshot_hash: str
    parameter_snapshot_hash: str
    dataset_manifest_ids: list
    contract_snapshot_id: str
    execution_model_id: str
    cost_scenario_id: str
    risk_policy_id: str
    trial_number: int = 1
    trial_budget: int = 12
    random_seed: int = 42
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def fingerprint(self) -> str:
        data = json.dumps(
            {
                "experiment_id": self.experiment_id,
                "strategy_snapshot_hash": self.strategy_snapshot_hash,
                "parameter_snapshot_hash": self.parameter_snapshot_hash,
                "dataset_manifest_ids": self.dataset_manifest_ids,
                "trial_number": self.trial_number,
                "random_seed": self.random_seed,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()


class ExperimentRegistry:
    def __init__(self, path: Path | None = None):
        self._path = path or _DEFAULT_REGISTRY_PATH
        self._experiments: dict[str, ExperimentRecord] = {}
        self._trial_counts: dict[str, int] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path) as f:
                data = json.load(f)
            for item in data.get("experiments", []):
                rec = ExperimentRecord(**item)
                self._experiments[rec.experiment_id] = rec
            self._trial_counts = data.get("trial_counts", {})
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    def _save_to_disk(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(
                {
                    "experiments": [vars(r) for r in self._experiments.values()],
                    "trial_counts": self._trial_counts,
                },
                f,
                indent=2,
            )

    def register(self, record: ExperimentRecord) -> str:
        if record.experiment_id in self._experiments:
            raise ValueError(f"Experiment {record.experiment_id} already registered")
        self._experiments[record.experiment_id] = record
        self._trial_counts[record.experiment_id] = self._trial_counts.get(record.experiment_id, 0) + 1
        self._save_to_disk()
        return record.experiment_id

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        return self._experiments.get(experiment_id)

    def list_by_strategy(self, strategy_hash: str) -> list[ExperimentRecord]:
        return [e for e in self._experiments.values() if e.strategy_snapshot_hash == strategy_hash]

    def count(self) -> int:
        return len(self._experiments)

    def check_budget(self, strategy_hash: str, budget: int = 12) -> bool:
        count = sum(1 for e in self._experiments.values() if e.strategy_snapshot_hash == strategy_hash)
        return count < budget
