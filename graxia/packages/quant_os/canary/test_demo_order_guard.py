"""Tests for demo order guard."""
from graxia.packages.quant_os.canary.demo_order_guard import DemoOrderGuard, OrderIntent


def _buy_intent():
    return OrderIntent(
        signal_id="SIG001", symbol="XAUUSD", side="BUY",
        volume=0.01, entry_price=2350.50, stop_loss=2348.50,
        take_profit=2354.50,
    )


def test_guard_allows_valid():
    guard = DemoOrderGuard()
    intent = _buy_intent()
    ok, issues = guard.preflight(intent)
    assert ok


def test_guard_rejects_duplicate():
    guard = DemoOrderGuard()
    intent = _buy_intent()
    guard.mark_submitted(intent)
    ok, issues = guard.preflight(intent)
    assert not ok
    assert any("duplicate" in i for i in issues)


def test_guard_rejects_missing_sl():
    guard = DemoOrderGuard()
    intent = _buy_intent()
    intent.stop_loss = 0
    ok, issues = guard.preflight(intent)
    assert not ok
    assert any("stop_loss" in i for i in issues)


def test_guard_rejects_invalid_sl():
    guard = DemoOrderGuard()
    intent = _buy_intent()
    intent.stop_loss = 2355.00  # above entry for BUY
    ok, issues = guard.preflight(intent)
    assert not ok


def test_guard_rejects_missing_tp():
    guard = DemoOrderGuard()
    intent = _buy_intent()
    intent.take_profit = 0
    intent.time_stop_minutes = 0
    ok, issues = guard.preflight(intent)
    assert not ok
