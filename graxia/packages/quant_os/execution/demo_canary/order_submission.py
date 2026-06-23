"""
SOLE ALLOWLISTED ORDER SUBMISSION LOCATION.

No other file may import order_send, TRADE_ACTION_DEAL, TRADE_ACTION_PENDING,
TRADE_ACTION_REMOVE, TRADE_ACTION_SLTP, or TRADE_ACTION_MODIFY.

This file is NOT YET reachable from any runtime path.
It will be activated only during G3 (First Demo Canary) after human approval.
"""
from typing import Optional

# This module is locked. Do not enable until G3.
__submission_enabled = False

def is_submission_enabled() -> bool:
    return __submission_enabled

# Future implementation (G3):
# - Accepts immutable DemoCanaryPlan only
# - Calls order_send exactly once
# - Records receipt
# - Never retries
