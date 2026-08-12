"""Phase 7 — Position and deal reconciliation."""
from dataclasses import dataclass


@dataclass
class ReconciliationResult:
    position_reconciled: bool
    deal_reconciled: bool
    position_count: int
    expected_position_count: int
    mismatch: bool


def reconcile_positions(
    broker_positions: list[dict],
    expected_positions: list[dict],
) -> ReconciliationResult:
    """Reconcile broker positions against expected positions."""
    broker_count = len(broker_positions)
    expected_count = len(expected_positions)

    count_match = broker_count == expected_count

    return ReconciliationResult(
        position_reconciled=count_match,
        deal_reconciled=count_match,
        position_count=broker_count,
        expected_position_count=expected_count,
        mismatch=not count_match,
    )
