"""Phase 7 — Protective stop verification and position reconciliation tests."""
from graxia.packages.quant_os.canary.protective_stop_verifier import verify_protective_stops
from graxia.packages.quant_os.canary.position_reconciler import reconcile_positions


def test_protective_stop_verified():
    result = verify_protective_stops(
        broker_sl=1.1000, expected_sl=1.1000,
        broker_tp=1.2000, expected_tp=1.2000,
    )
    assert result.verified is True
    assert result.mismatch is False


def test_protective_stop_mismatch():
    result = verify_protective_stops(
        broker_sl=1.1000, expected_sl=1.1100,
        broker_tp=0.0, expected_tp=0.0,
    )
    assert result.verified is False
    assert result.mismatch is True


def test_position_reconciled():
    result = reconcile_positions(
        broker_positions=[{"id": 1}, {"id": 2}],
        expected_positions=[{"id": 1}, {"id": 2}],
    )
    assert result.position_reconciled is True
    assert result.mismatch is False


def test_position_mismatch():
    result = reconcile_positions(
        broker_positions=[{"id": 1}],
        expected_positions=[{"id": 1}, {"id": 2}],
    )
    assert result.position_reconciled is False
    assert result.mismatch is True
