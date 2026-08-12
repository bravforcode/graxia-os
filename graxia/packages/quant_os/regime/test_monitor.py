"""Tests for Execution Monitor."""
import sys
sys.path.insert(0, r'C:\Users\menum\graxia os')
from graxia.packages.quant_os.regime.monitor import (
    Monitor, OrderReport, FillReport, HealthStatus,
)


def test_healthy():
    m = Monitor()
    s = m.get_status()
    assert s.health_status == HealthStatus.HEALTHY
    assert s.reason_code == "HEALTHY"
    assert s.total_trades == 0
    print(f"  [OK] Healthy: {s.health_status}")


def test_report_order_and_fill():
    m = Monitor()
    o = OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                    session="LONDON", expected_price=1.10500, stop_loss=1.10300,
                    take_profit=1.10900, risk_usd=250)
    m.report_order(o)

    f = FillReport(symbol="EURUSD", side="BUY", fill_price=1.10505,
                   fill_quantity=10000, fill_pnl=50, latency_ms=150,
                   spread_at_fill=0.0002)
    m.report_fill(f)

    s = m.get_status()
    assert s.total_trades == 1
    assert s.health_status == HealthStatus.HEALTHY
    assert s.fill_stats.total_attempts == 1
    assert s.fill_stats.total_fills == 1
    assert s.fill_stats.fill_rate == 1.0
    assert s.slippage_stats.total_bps.count == 1
    print(f"  [OK] Order+fill: {s.total_trades} trades, rate={s.fill_stats.fill_rate}")


def test_slippage_alert():
    m = Monitor(slippage_critical_bps=3.0)
    for i in range(5):
        m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                    session="LONDON", expected_price=1.10500 + i * 0.001,
                                    stop_loss=1.100, take_profit=1.110, risk_usd=250))
        m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.10500 + i * 0.001,  # no slippage
                                  fill_quantity=10000, latency_ms=100))
    # Now a bad fill
    m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                session="LONDON", expected_price=1.10500,
                                stop_loss=1.100, take_profit=1.110, risk_usd=250))
    m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.11000,  # 45 bps slippage
                              fill_quantity=10000, latency_ms=100))

    s = m.get_status()
    assert s.health_status == HealthStatus.CRITICAL, f"Should be critical: {s.reason_code}"
    assert "slippage" in s.reason_code.lower()
    print(f"  [OK] Slippage alert: {s.reason_code}")


def test_fill_rate_alert():
    m = Monitor(min_fill_rate=0.51, fill_rate_warning=0.70, rejection_rate_critical=0.90)
    for i in range(10):
        m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                    session="LONDON", expected_price=1.105, stop_loss=1.10,
                                    take_profit=1.11, risk_usd=250))
        # Only report fill for 5 of 10 orders (simulates unfilled orders)
        if i < 5:
            m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.105,
                                      fill_quantity=10000, latency_ms=100))

    s = m.get_status()
    # 10 orders, 5 fills -> fill_rate = 0.5
    fill_rate = s.fill_stats.fill_rate
    assert fill_rate == 0.5, f"Expected 0.5, got {fill_rate}"
    # 0.5 < 0.51 → CRITICAL
    assert s.health_status == HealthStatus.CRITICAL, f"Status={s.health_status}"
    print(f"  [OK] Fill rate: {fill_rate:.1%} -> {s.health_status}")


def test_latency_alert():
    m = Monitor(latency_critical_ms=500)
    for i in range(5):
        m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                    session="LONDON", expected_price=1.105, stop_loss=1.10,
                                    take_profit=1.11, risk_usd=250))
        m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.105,
                                  fill_quantity=10000, latency_ms=800 + i * 10))

    s = m.get_status()
    assert s.health_status == HealthStatus.CRITICAL, f"Should be critical: {s.reason_code}"
    print(f"  [OK] Latency alert: avg={s.latency_stats.ms.mean:.0f}ms -> {s.reason_code}")


def test_rejection_alert():
    m = Monitor(rejection_rate_critical=0.30)
    for i in range(10):
        m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                    session="LONDON", expected_price=1.105, stop_loss=1.10,
                                    take_profit=1.11, risk_usd=250))
        rejected = i < 4  # 40% rejection
        m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.105,
                                  fill_quantity=10000, rejected=rejected,
                                  rejection_reason="INVALID_PRICE" if rejected else ""))

    s = m.get_status()
    assert s.health_status == HealthStatus.CRITICAL, f"Should be critical: {s.reason_code}"
    print(f"  [OK] Rejection alert: {s.reason_code}")


def test_divergence_alert():
    m = Monitor(divergence_critical=5.0)
    for i in range(5):
        m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                    session="LONDON", expected_price=1.105, stop_loss=1.10,
                                    take_profit=1.11, risk_usd=250))
        m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.105,
                                  fill_quantity=10000, fill_pnl=50, latency_ms=100,
                                  expected_pnl=100))  # 50% diff

    s = m.get_status()
    assert s.health_status == HealthStatus.CRITICAL, f"Should be critical: {s.reason_code}"
    assert "divergence" in s.reason_code.lower()
    print(f"  [OK] Divergence alert: score={s.divergence.score} -> {s.reason_code}")


def test_drawdown():
    m = Monitor(initial_balance=10000)
    m._peak_balance = 10000
    m._current_balance = 9000
    dd = m._compute_drawdown()
    assert dd == 10.0, f"Drawdown should be 10%: {dd}"
    s = m.get_status()
    assert s.drawdown_pct == 10.0
    print(f"  [OK] Drawdown: {dd}%")


def test_alerts_consume():
    m = Monitor(slippage_critical_bps=1.0)
    for i in range(5):
        m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                    session="LONDON", expected_price=1.105, stop_loss=1.10,
                                    take_profit=1.11, risk_usd=250))
        m.report_fill(FillReport(symbol="EURUSD", side="BUY",
                                  fill_price=1.115 + i * 0.01,
                                  fill_quantity=10000, latency_ms=100))
    s = m.get_status()
    assert s.health_status == HealthStatus.CRITICAL, "Should be critical"
    assert len(s.alerts) > 0, "Status should include alerts"
    # Consume alerts (acknowledge them)
    consumed = m.get_alerts(clear=True)
    assert len(consumed) > 0, "Should have alerts to consume"
    # Status still critical because thresholds still exceeded (alerts regen on next get_status)
    s2 = m.get_status()
    assert s2.health_status == HealthStatus.CRITICAL, "Still critical (thresholds unchanged)"
    print(f"  [OK] Alerts consumed: {len(consumed)} alerts")


def test_reset():
    m = Monitor()
    m.report_order(OrderReport(symbol="EURUSD", side="BUY", signal_type="REVERSAL",
                                session="LONDON", expected_price=1.105, stop_loss=1.10,
                                take_profit=1.11, risk_usd=250))
    m.report_fill(FillReport(symbol="EURUSD", side="BUY", fill_price=1.105,
                              fill_quantity=10000, latency_ms=100))
    assert m.get_status().total_trades == 1
    m.reset()
    s = m.get_status()
    assert s.total_trades == 0
    assert s.slippage_stats.total_bps.count == 0
    assert s.health_status == HealthStatus.HEALTHY
    print(f"  [OK] Reset: trades={s.total_trades}")


def test_symbol_breakdown():
    m = Monitor()
    for sym, side, price in [("EURUSD", "BUY", 1.105), ("GBPUSD", "SELL", 1.250),
                              ("EURUSD", "BUY", 1.106)]:
        m.report_order(OrderReport(symbol=sym, side=side, signal_type="REVERSAL",
                                    session="LONDON", expected_price=price,
                                    stop_loss=price*0.99, take_profit=price*1.01,
                                    risk_usd=250))
        m.report_fill(FillReport(symbol=sym, side=side, fill_price=price,
                                  fill_quantity=10000, latency_ms=100))

    s = m.get_status()
    assert len(s.slippage_stats.by_symbol) == 2
    assert s.slippage_stats.by_symbol["EURUSD"].count == 2
    assert s.slippage_stats.by_symbol["GBPUSD"].count == 1
    print(f"  [OK] Symbol breakdown: EURUSD={s.slippage_stats.by_symbol['EURUSD'].count}"
          f" GBPUSD={s.slippage_stats.by_symbol['GBPUSD'].count}")


if __name__ == "__main__":
    print("=== Monitor Tests ===\n")
    test_healthy()
    test_report_order_and_fill()
    test_slippage_alert()
    test_fill_rate_alert()
    test_latency_alert()
    test_rejection_alert()
    test_divergence_alert()
    test_drawdown()
    test_alerts_consume()
    test_reset()
    test_symbol_breakdown()
    print("\n=== All tests passed ===")
