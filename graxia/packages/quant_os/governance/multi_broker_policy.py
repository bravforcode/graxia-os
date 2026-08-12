"""Phase 11 — Multi-broker policy."""
from dataclasses import dataclass, field


@dataclass
class BrokerRequirements:
    independent_contract_spec: bool = True
    broker_specific_execution: bool = True
    separate_demo_lifecycle: bool = True
    separate_cost_observation: bool = True
    independent_reconciliation: bool = True
    credential_boundary: bool = True
    broker_specific_runbook: bool = True
    no_shared_idempotency: bool = True

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        for field_name, value in self.__dict__.items():
            if not value:
                issues.append(f"{field_name} must be True")
        return len(issues) == 0, issues


@dataclass
class MultiBrokerPolicy:
    brokers: list = field(default_factory=list)

    def add_broker(self, name: str, requirements: BrokerRequirements) -> None:
        self.brokers.append({"name": name, "requirements": requirements})

    def count(self) -> int:
        return len(self.brokers)
