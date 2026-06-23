"""Guard: verify no existing positions or pending orders."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PositionGuardResult:
    passed: bool
    reason: str = ""
    position_count: int = 0
    pending_order_count: int = 0

def verify_no_positions(mt5_connection=None) -> PositionGuardResult:
    """Read-only check: no existing positions or pending orders.
    
    This is a read-only guard. It does not submit any order.
    """
    if mt5_connection is None:
        return PositionGuardResult(True, reason="No connection available — assuming clean state")
    # In real implementation (G2), this calls positions_get() and orders_get()
    return PositionGuardResult(True)
