"""Tests for Risk Overlay."""
import sys
sys.path.insert(0, r'C:\Users\menum\graxia os')
from datetime import datetime, timedelta
from graxia.packages.quant_os.regime.risk_overlay import RiskOverlay


def test_approve_trade():
    ro = RiskOverlay(initial_balance=50000, max_risk_pct=0.005)
    result = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert result.approved, f"Should approve: {result.reason_code}"
    assert result.position_size > 0
    assert result.risk_usd == 250
    print(f"  [OK] Trade approved: risk=${result.risk_usd} size={result.position_size}")


def test_max_risk_cap():
    ro = RiskOverlay(initial_balance=50000, max_risk_pct=0.005)
    result = ro.approve(risk_amount=500, stop_distance=0.0009, current_balance=50000)
    # 500/50000 = 1% which is > 0.55%
    assert not result.approved, f"Should reject excess risk: {result.reason_code}"
    print(f"  [OK] Risk cap exceeded: {result.reason_code}")


def test_daily_loss_limit():
    ro = RiskOverlay(initial_balance=50000, max_daily_loss_pct=0.02)
    # Report losses until daily limit hit
    ro.report_trade_result(-500)  # -1%
    ro.report_trade_result(-500)  # -2% → should trigger kill switch
    assert ro.state.kill_switch_triggered, "Kill switch should trigger"
    result = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=49000)
    assert not result.approved, f"Should reject after daily loss: {result.reason_code}"
    print(f"  [OK] Daily loss limit: {result.reason_code} ks={ro.state.kill_switch_reason}")


def test_consecutive_loss_cooldown():
    ro = RiskOverlay(initial_balance=50000, max_consecutive_losses=2, cooldown_minutes=30)
    ro.report_trade_result(-100)
    assert ro.state.consecutive_losses == 1, "1 loss"
    r1 = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert r1.approved, "Should still approve after 1 loss"

    ro.report_trade_result(-100)
    assert ro.state.consecutive_losses == 2, "2 losses"
    assert ro.state.cooldown_until is not None, "Cooldown should be set"
    r2 = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert not r2.approved, f"Should block during cooldown: {r2.reason_code}"
    assert r2.cooldown_active
    print(f"  [OK] Consecutive loss cooldown: {r2.reason_code}")


def test_win_resets_consecutive():
    ro = RiskOverlay(initial_balance=50000, max_consecutive_losses=2)
    ro.report_trade_result(-100)  # loss 1
    ro.report_trade_result(+200)  # win → reset
    assert ro.state.consecutive_losses == 0, "Win should reset counter"
    result = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert result.approved, "Should approve after win"
    print(f"  [OK] Win resets consecutive counter: {ro.state.consecutive_losses}")


def test_weekly_loss():
    # Raise daily limit so weekly test isn't blocked by daily limit
    ro = RiskOverlay(initial_balance=50000, max_daily_loss_pct=0.10, max_weekly_loss_pct=0.05)
    ro.report_trade_result(-2000)  # -4%
    result = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=48000)
    assert result.approved, "Should approve at -4% (within 5%)"

    ro.report_trade_result(-1000)  # -6% total → should trigger
    assert ro.state.kill_switch_triggered, "Kill switch should trigger at -5%+"
    result2 = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=47000)
    assert not result2.approved, f"Should reject at -6%: {result2.reason_code}"
    print(f"  [OK] Weekly loss limit: {result2.reason_code}")


def test_weekly_reset():
    ro = RiskOverlay(initial_balance=50000, max_weekly_loss_pct=0.05)
    ro.state.weekly_start = datetime.now() - timedelta(days=30)
    ro.state.weekly_realized_pnl = -2000
    ro._reset_if_new_period()
    # Only resets on Monday; verify run without error
    expected = 0 if datetime.now().weekday() == 0 else -2000
    assert ro.state.weekly_realized_pnl == expected, (
        f"expected={expected} got={ro.state.weekly_realized_pnl}"
        f" weekday={datetime.now().weekday()}")
    print(f"  [OK] Weekly reset: {ro.state.weekly_realized_pnl} (weekday={datetime.now().weekday()})")


def test_max_daily_trades():
    ro = RiskOverlay(initial_balance=50000, max_daily_trades=3)
    for i in range(3):
        ro.report_trade_result(+50)
    assert ro.state.trade_count_today == 3
    result = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert not result.approved, f"Should reject at max trades: {result.reason_code}"
    print(f"  [OK] Max daily trades: {result.reason_code}")


def test_kill_switch_manual():
    ro = RiskOverlay(initial_balance=50000)
    ro.trigger_kill_switch("MANUAL")
    result = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert not result.approved, "Should reject when kill switch active"
    assert result.kill_switch_active
    print(f"  [OK] Manual kill switch: {result.reason_code}")

    ro.release_kill_switch()
    result2 = ro.approve(risk_amount=250, stop_distance=0.0009, current_balance=50000)
    assert result2.approved, "Should approve after release"
    print("  [OK] Kill switch released")


def test_get_status():
    ro = RiskOverlay(initial_balance=50000)
    ro.report_trade_result(-200)
    ro.report_trade_result(-300)
    s = ro.get_status()
    assert s["daily_pnl"] == -500
    assert s["consecutive_losses"] == 2
    assert not s["kill_switch"]
    print(f"  [OK] Status: daily={s['daily_pnl']} consec={s['consecutive_losses']}")


if __name__ == "__main__":
    print("=== Risk Overlay Tests ===\n")
    test_approve_trade()
    test_max_risk_cap()
    test_daily_loss_limit()
    test_consecutive_loss_cooldown()
    test_win_resets_consecutive()
    test_weekly_loss()
    test_weekly_reset()
    test_max_daily_trades()
    test_kill_switch_manual()
    test_get_status()
    print("\n=== All tests passed ===")
