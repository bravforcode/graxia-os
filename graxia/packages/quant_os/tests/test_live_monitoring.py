"""Tests for live monitoring modules: prometheus_metrics, alert_rules, live_dashboard."""

import pytest
import time

from graxia.packages.quant_os.monitoring.prometheus_metrics import (
    TradeCounter,
    PnLHistogram,
    RiskGauge,
    LatencyHistogram,
    ExposureGauge,
    MetricsRegistry,
)
from graxia.packages.quant_os.monitoring.alert_rules import (
    Severity,
    Alert,
    HighDrawdownAlert,
    ConsecutiveLossAlert,
    SpreadWideningAlert,
    DataStalenessAlert,
    AlertEngine,
)
from graxia.packages.quant_os.monitoring.live_dashboard import (
    render_positions,
    render_pnl,
    render_risk,
    render_recent_trades,
    render_health,
    render_dashboard,
)


# ---------------------------------------------------------------------------
# Prometheus Metrics Format
# ---------------------------------------------------------------------------

class TestPrometheusMetricsFormat:
    def test_trade_counter_render_format(self):
        tc = TradeCounter()
        tc.inc("XAUUSD", "buy", "bos_choch")
        tc.inc("XAUUSD", "buy", "bos_choch")
        tc.inc("EURUSD", "sell", "trend")
        out = tc.render()
        assert "# TYPE quant_os_trades_total counter" in out
        assert 'symbol="XAUUSD"' in out
        assert 'symbol="EURUSD"' in out
        assert "quant_os_trades_total" in out

    def test_trade_counter_default_value_zero(self):
        tc = TradeCounter()
        assert tc.value("UNKNOWN") == 0

    def test_pnl_histogram_render_format(self):
        h = PnLHistogram()
        h.observe(10.5)
        h.observe(-3.2)
        out = h.render()
        assert "# TYPE quant_os_pnl histogram" in out
        assert "quant_os_pnl_bucket" in out
        assert "quant_os_pnl_sum" in out
        assert "quant_os_pnl_count 2" in out

    def test_pnl_histogram_buckets_correct(self):
        h = PnLHistogram()
        h.observe(0.0)
        out = h.render()
        assert 'le="0"' in out
        assert 'le="+Inf"' in out

    def test_risk_gauge_render_format(self):
        g = RiskGauge()
        g.set(42.5)
        out = g.render()
        assert "# TYPE quant_os_risk_level gauge" in out
        assert "quant_os_risk_level 42.5" in out

    def test_risk_gauge_clamps_to_0_100(self):
        g = RiskGauge()
        g.set(-10)
        assert g.get() == 0.0
        g.set(150)
        assert g.get() == 100.0

    def test_latency_histogram_render_format(self):
        h = LatencyHistogram()
        h.observe(0.015)
        h.observe(0.050)
        out = h.render()
        assert "# TYPE quant_os_latency_seconds histogram" in out
        assert "quant_os_latency_seconds_bucket" in out
        assert "quant_os_latency_seconds_count 2" in out

    def test_exposure_gauge_render_format(self):
        g = ExposureGauge()
        g.set(12345.67)
        out = g.render()
        assert "# TYPE quant_os_exposure gauge" in out
        assert "12345.67" in out

    def test_exposure_gauge_clamps_negative(self):
        g = ExposureGauge()
        g.set(-500)
        assert g.get() == 0.0

    def test_registry_render_combined(self):
        reg = MetricsRegistry()
        reg.trades.inc("XAUUSD", "buy", "test")
        reg.pnl.observe(5.0)
        reg.risk.set(30.0)
        reg.latency.observe(0.01)
        reg.exposure.set(5000.0)
        out = reg.render()
        assert "quant_os_trades_total" in out
        assert "quant_os_pnl" in out
        assert "quant_os_risk_level" in out
        assert "quant_os_latency_seconds" in out
        assert "quant_os_exposure" in out


# ---------------------------------------------------------------------------
# Alert Rules
# ---------------------------------------------------------------------------

class TestAlertRuleTrigger:
    def test_high_drawdown_fires(self):
        rule = HighDrawdownAlert(threshold_pct=5.0)
        alert = rule.check(6.5)
        assert alert is not None
        assert alert.severity == Severity.CRITICAL
        assert "6.50%" in alert.message

    def test_consecutive_loss_fires(self):
        rule = ConsecutiveLossAlert(max_losses=3)
        rule.update(-10.0)
        rule.update(-5.0)
        rule.update(-2.0)
        alert = rule.check()
        assert alert is not None
        assert alert.severity == Severity.WARNING
        assert "3 consecutive" in alert.message

    def test_spread_widening_fires(self):
        rule = SpreadWideningAlert(normal_spread_pips=1.0, multiplier=3.0)
        alert = rule.check(5.0)
        assert alert is not None
        assert "5.00" in alert.message

    def test_data_staleness_fires(self):
        rule = DataStalenessAlert(max_age_seconds=60.0)
        alert = rule.check(120.0)
        assert alert is not None
        assert alert.severity == Severity.CRITICAL

    def test_alert_str_representation(self):
        alert = Alert(
            rule_name="test_rule",
            severity=Severity.WARNING,
            message="test message",
        )
        s = str(alert)
        assert "[WARNING]" in s
        assert "test_rule" in s
        assert "test message" in s

    def test_alert_engine_evaluate(self):
        engine = AlertEngine()
        engine.add_rule(HighDrawdownAlert(threshold_pct=5.0))
        engine.add_rule(SpreadWideningAlert(normal_spread_pips=1.0, multiplier=3.0))
        alerts = engine.evaluate(drawdown_pct=7.0, spread_pips=0.5)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "high_drawdown"

    def test_alert_engine_history(self):
        engine = AlertEngine()
        engine.add_rule(HighDrawdownAlert(threshold_pct=2.0))
        engine.evaluate(drawdown_pct=3.0)
        engine.evaluate(drawdown_pct=1.0)
        engine.evaluate(drawdown_pct=5.0)
        assert len(engine.history) == 2


class TestAlertRuleNoFalsePositive:
    def test_high_drawdown_no_fire(self):
        rule = HighDrawdownAlert(threshold_pct=5.0)
        assert rule.check(3.0) is None
        assert rule.check(5.0) is None

    def test_consecutive_loss_resets_on_win(self):
        rule = ConsecutiveLossAlert(max_losses=3)
        rule.update(-10.0)
        rule.update(-5.0)
        rule.update(10.0)  # win resets streak
        rule.update(-2.0)
        assert rule.streak == 1
        assert rule.check() is None

    def test_consecutive_loss_no_fire_under_threshold(self):
        rule = ConsecutiveLossAlert(max_losses=5)
        rule.update(-10.0)
        rule.update(-5.0)
        assert rule.streak == 2
        assert rule.check() is None

    def test_spread_widening_no_fire(self):
        rule = SpreadWideningAlert(normal_spread_pips=1.0, multiplier=3.0)
        assert rule.check(2.0) is None
        assert rule.check(3.0) is None

    def test_data_staleness_no_fire(self):
        rule = DataStalenessAlert(max_age_seconds=60.0)
        assert rule.check(30.0) is None
        assert rule.check(60.0) is None


# ---------------------------------------------------------------------------
# Dashboard Render
# ---------------------------------------------------------------------------

class TestDashboardRender:
    def test_render_positions_empty(self):
        out = render_positions([])
        assert "no open positions" in out

    def test_render_positions_with_data(self):
        positions = [
            {"symbol": "XAUUSD", "side": "buy", "entry_price": 2350.5, "pnl": 12.3},
        ]
        out = render_positions(positions)
        assert "XAUUSD" in out
        assert "BUY" in out

    def test_render_pnl(self):
        out = render_pnl(45.8, 62.5, 8)
        assert "+45.80" in out
        assert "62.5%" in out
        assert "8" in out

    def test_render_pnl_negative(self):
        out = render_pnl(-10.5, 40.0, 5)
        assert "-10.50" in out

    def test_render_risk(self):
        out = render_risk(35.0, 1500.0)
        assert "[#" in out
        assert "35/100" in out
        assert "1500.00" in out

    def test_render_recent_trades_empty(self):
        out = render_recent_trades([])
        assert "no recent trades" in out

    def test_render_recent_trades_with_data(self):
        trades = [
            {"timestamp": time.time() - 300, "symbol": "XAUUSD", "side": "buy", "pnl": 12.3},
        ]
        out = render_recent_trades(trades)
        assert "XAUUSD" in out

    def test_render_health(self):
        out = render_health("connected", 12.5, 3.0)
        assert "connected" in out
        assert "12.5ms" in out
        assert "3.0s" in out

    def test_render_health_with_alerts(self):
        out = render_health("disconnected", 100.0, 120.0, ["Feed down"])
        assert "!! Feed down" in out

    def test_render_dashboard_full(self):
        out = render_dashboard(
            positions=[{"symbol": "XAUUSD", "side": "buy", "entry_price": 2350.0, "pnl": 5.0}],
            pnl=45.8,
            win_rate=62.5,
            trades_count=8,
            risk_level=35.0,
            exposure=1500.0,
            recent_trades=[{"timestamp": time.time(), "symbol": "XAUUSD", "side": "buy", "pnl": 5.0}],
            feed_status="connected",
            latency_ms=12.0,
            data_age_s=2.0,
        )
        assert "QUANT OS LIVE DASHBOARD" in out
        assert "POSITIONS" in out
        assert "PnL SUMMARY" in out
        assert "RISK" in out
        assert "RECENT TRADES" in out
        assert "SYSTEM HEALTH" in out

    def test_render_dashboard_minimal(self):
        out = render_dashboard()
        assert "QUANT OS LIVE DASHBOARD" in out
        assert "no open positions" in out
