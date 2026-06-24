"""
SOLE ALLOWLISTED ORDER SUBMISSION LOCATION.

No other file may import order_send, TRADE_ACTION_DEAL, TRADE_ACTION_PENDING,
TRADE_ACTION_REMOVE, TRADE_ACTION_SLTP, or TRADE_ACTION_MODIFY.

G4.0 one-shot: submit_order_once() is the only function that calls order_send.
G4.2 one-shot: submit_close_once() is the only function that calls position_close.
Enabled via enable_submission() / disabled via disable_submission().
Default locked (submission disabled).
"""
from enum import Enum, auto
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


class CloseState(Enum):
    IDLE = auto()
    CLOSE_PENDING = auto()
    CLOSE_APPROVED = auto()
    CLOSING = auto()
    CLOSE_CONFIRMED = auto()
    CLOSE_FAILED = auto()
    CLOSE_UNCERTAIN = auto()


def submit_close_once(position_ticket: int, expected_magic: int, deviation: int = 20) -> dict:
    """One-shot position close. No retry.

    Must only be called when is_submission_enabled() is True.
    Verifies position exists and magic matches expected (ownership check).
    Calls mt5.position_close() exactly once — never retries.
    Returns structured evidence dict.
    """
    if not __submission_enabled:
        return {"retcode": -999, "error": "SUBMISSION_DISABLED", "comment": "order_submission is locked"}

    # ponytail: single positions_get(ticket=X) for existence + ownership check
    positions = mt5.positions_get(ticket=position_ticket)
    if not positions or len(positions) == 0:
        return {"retcode": -2, "error": "POSITION_NOT_FOUND", "comment": "position ticket not found — may already be closed"}

    pos = positions[0]
    # ponytail: magic check only. The magic was set by submit_order_once's order_send request.
    if expected_magic and pos.magic != expected_magic:
        return {"retcode": -3, "error": "POSITION_MAGIC_MISMATCH",
                "comment": f"expected magic {expected_magic}, got {pos.magic}"}

    result = mt5.position_close(ticket=position_ticket, deviation=deviation)

    if result is None:
        return {"retcode": -1, "error": "CLOSE_UNKNOWN", "comment": "position_close returned None — ambiguous state, no retry"}

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
