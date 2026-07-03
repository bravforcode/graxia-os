"""Phase 7 — Protective stop verification after order fill."""
from dataclasses import dataclass


@dataclass
class ProtectiveStopResult:
    verified: bool
    broker_stop_loss: float
    expected_stop_loss: float
    broker_take_profit: float
    expected_take_profit: float
    mismatch: bool


def verify_protective_stops(
    broker_sl: float,
    expected_sl: float,
    broker_tp: float,
    expected_tp: float,
    tolerance: float = 0.0001,
) -> ProtectiveStopResult:
    """Verify broker protective stops match expected values."""
    sl_mismatch = abs(broker_sl - expected_sl) > tolerance
    tp_mismatch = abs(broker_tp - expected_tp) > tolerance if expected_tp > 0 else False

    return ProtectiveStopResult(
        verified=not sl_mismatch and not tp_mismatch,
        broker_stop_loss=broker_sl,
        expected_stop_loss=expected_sl,
        broker_take_profit=broker_tp,
        expected_take_profit=expected_tp,
        mismatch=sl_mismatch or tp_mismatch,
    )
