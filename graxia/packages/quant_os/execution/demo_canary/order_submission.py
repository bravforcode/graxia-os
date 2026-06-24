"""
SOLE ALLOWLISTED ORDER SUBMISSION LOCATION.

No other file may import order_send, TRADE_ACTION_DEAL, TRADE_ACTION_PENDING,
TRADE_ACTION_REMOVE, TRADE_ACTION_SLTP, or TRADE_ACTION_MODIFY.

G4.0 one-shot: submit_order_once() is the only function that calls order_send.
Enabled via enable_submission() / disabled via disable_submission().
Default locked (submission disabled).
"""
from typing import Optional
import MetaTrader5 as mt5

# This module is locked by default. Enable only for one-shot G4.0.
__submission_enabled = False


def is_submission_enabled() -> bool:
    return __submission_enabled


def enable_submission() -> None:
    """Explicitly enable one-shot submission. Call just before order_send."""
    global __submission_enabled
    __submission_enabled = True


def disable_submission() -> None:
    """Disable submission immediately after order_send attempt."""
    global __submission_enabled
    __submission_enabled = False


def submit_order_once(request: dict) -> dict:
    """Call order_send exactly once. Never retry.

    Must only be called when is_submission_enabled() is True.
    Returns a plain dict with retcode + result fields.
    If result is None (ambiguous), returns SUBMISSION_UNKNOWN.
    """
    if not __submission_enabled:
        return {"retcode": -999, "error": "SUBMISSION_DISABLED", "comment": "order_submission is locked"}

    result = mt5.order_send(request)

    if result is None:
        return {"retcode": -1, "error": "SUBMISSION_UNKNOWN", "comment": "order_send returned None — ambiguous state"}

    return {
        "retcode": result.retcode,
        "deal": result.deal,
        "order": result.order,
        "volume": result.volume,
        "price": result.price,
        "comment": result.comment,
        "request_id": result.request_id,
        "retcode_external": result.retcode_external,
    }
