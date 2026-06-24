"""
Guard: margin estimate + order_check wrapper.
 
READ-ONLY. Fail-closed. No order_send.
order_check() result is labelled PRECHECK_ONLY, NOT_EXECUTION_PROOF.
"""
from dataclasses import dataclass
from typing import Optional

MARGIN_CAP_PERCENT = 1.0  # Max margin as % of balance

@dataclass(frozen=True)
class MarginGuardResult:
    passed: bool
    reason: str = ""
    margin_estimate: float = 0.0
    margin_cap: float = 0.0
    balance: float = 0.0

@dataclass(frozen=True)
class OrderCheckResult:
    passed: bool
    reason: str = ""
    retcode: int = 0
    comment: str = ""
    label: str = "PRECHECK_ONLY, NOT_EXECUTION_PROOF"


def verify_margin(
    margin_estimate: float,
    balance: float,
    margin_cap_pct: float = MARGIN_CAP_PERCENT
) -> MarginGuardResult:
    """Verify margin is within cap."""
    if margin_estimate is None or margin_estimate < 0:
        return MarginGuardResult(False, f"Invalid margin estimate: {margin_estimate}")
    if balance <= 0:
        return MarginGuardResult(False, f"Invalid balance: {balance}")
    
    margin_cap = balance * (margin_cap_pct / 100.0)
    if margin_estimate > margin_cap:
        return MarginGuardResult(
            False,
            f"Margin {margin_estimate:.2f} exceeds cap {margin_cap:.2f} ({margin_cap_pct}% of {balance:.2f})",
            margin_estimate=margin_estimate,
            margin_cap=margin_cap,
            balance=balance,
        )
    
    return MarginGuardResult(True, margin_estimate=margin_estimate, margin_cap=margin_cap, balance=balance)


def verify_order_check(order_check_data: Optional[dict]) -> OrderCheckResult:
    """Wrapper for MT5 order_check(). 
    
    IMPORTANT: order_check() passing does NOT guarantee execution.
    Label must always be PRECHECK_ONLY, NOT_EXECUTION_PROOF.
    """
    if order_check_data is None:
        return OrderCheckResult(False, "No order_check data available", label="PRECHECK_ONLY, NOT_EXECUTION_PROOF")
    
    retcode = order_check_data.get("retcode", -1)
    comment = order_check_data.get("comment", "")
    
    if retcode != 0:
        return OrderCheckResult(
            False,
            f"order_check failed: retcode={retcode}, {comment}",
            retcode=retcode,
            comment=comment,
            label="PRECHECK_ONLY, NOT_EXECUTION_PROOF",
        )
    
    return OrderCheckResult(
        True,
        f"order_check passed: {comment}",
        retcode=retcode,
        comment=comment,
        label="PRECHECK_ONLY, NOT_EXECUTION_PROOF",
    )
