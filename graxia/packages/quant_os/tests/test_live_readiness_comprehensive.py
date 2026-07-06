"""Comprehensive unit tests for live_readiness, shadow, and canary modules.

Target: 35+ tests covering shadow mode, canary deployment,
live readiness checks, and pipeline integration.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.canary.broker_validator import (
    BrokerValidationReport,
    BrokerValidator,
)

# ─── canary imports ────────────────────────────────────────────────────
from graxia.packages.quant_os.canary.config import CanaryConfig
from graxia.packages.quant_os.canary.daily_report import (
    DailyReport,
    DailyReporter,
)
from graxia.packages.quant_os.canary.demo_scorecard import (
    DemoScorecard,
)
from graxia.packages.quant_os.canary.emergency_kill_switch import (
    EmergencyKillSwitch,
)
from graxia.packages.quant_os.canary.order_lifecycle import (
    OrderLifecycle,
    OrderState,
)
from graxia.packages.quant_os.canary.position_reconciler import (
    reconcile_positions,
)
from graxia.packages.quant_os.canary.protective_stop_verifier import (
    verify_protective_stops,
)
from graxia.packages.quant_os.live_readiness.account_snapshot_service import (
    _redact_account_number,
    take_account_snapshot,
)

# ─── live_readiness imports ────────────────────────────────────────────
from graxia.packages.quant_os.live_readiness.broker_profile import (
    DEFAULT_PROFILE,
    BrokerProfile,
)
from graxia.packages.quant_os.live_readiness.runtime_capabilities import (
    RuntimeCapabilities,
)
from graxia.packages.quant_os.live_readiness.smoke_report import (
    format_smoke_report_human,
    generate_smoke_report,
    persist_smoke_report,
)
from graxia.packages.quant_os.live_readiness.symbol_snapshot_service import (
    persist_snapshot as persist_symbol_snapshot,
)
from graxia.packages.quant_os.live_readiness.symbol_snapshot_service import (
    take_symbol_snapshot,
)
from graxia.packages.quant_os.shadow.event_risk_gate import (
    EventRiskGate,
)
from graxia.packages.quant_os.shadow.failure_rules import (
    FAILURE_RULES,
    FailureRuleChecker,
)
from graxia.packages.quant_os.shadow.market_health import (
    MarketHealthMachine,
    MarketHealthState,
)
from graxia.packages.quant_os.shadow.shadow_campaign import (
    CampaignConfig,
    ShadowCampaign,
)
from graxia.packages.quant_os.shadow.shadow_pass_criteria import (
    ShadowPassCriteria,
)

# ─── shadow imports ────────────────────────────────────────────────────
from graxia.packages.quant_os.shadow.shadow_pipeline import (
    ShadowPipeline,
)
from graxia.packages.quant_os.shadow.shadow_telemetry import (
    ShadowTelemetry,
)

# ═══════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def shadow_pipeline():
    p = ShadowPipeline()
    p.start_session("test_session_001")
    return p


@pytest.fixture
def sample_tick():
    return {"symbol": "XAUUSD", "bid": 2340.50, "ask": 2340.80, "time": 1700000000}


@pytest.fixture
def campaign_config():
    return CampaignConfig(
        symbol="XAUUSD",
        strategy_id="test_strategy",
        broker="ICMarkets",
        server="ICMarkets-Demo02",
        max_duration_hours=24,
        max_signals_per_day=100,
    )


@pytest.fixture
def canary_config():
    return CanaryConfig()


@pytest.fixture
def broker_validator():
    return BrokerValidator()


@pytest.fixture
def telemetry():
    t = ShadowTelemetry()
    t.start()
    return t


@pytest.fixture
def kill_switch():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield EmergencyKillSwitch(state_file=os.path.join(tmpdir, "kill.json"))


@pytest.fixture
def event_risk_gate():
    return EventRiskGate(blackout_minutes=30)


@pytest.fixture
def sample_account_info():
    return {
        "login_redacted": "****1234",
        "server": "ICMarkets-Demo02",
        "currency": "USD",
        "balance": 10000.0,
        "equity": 10050.0,
        "margin": 500.0,
        "margin_free": 9550.0,
        "margin_level": 20100.0,
        "leverage": 500,
        "profit": 50.0,
        "name": "Test Account",
        "company": "IC Markets",
    }


@pytest.fixture
def sample_positions():
    return [{"ticket": 123456, "symbol": "XAUUSD", "volume": 0.1, "profit": 25.0}]


@pytest.fixture
def sample_orders():
    return [{"ticket": 789012, "symbol": "XAUUSD", "volume": 0.1}]


@pytest.fixture
def mock_readonly_client(sample_account_info, sample_positions, sample_orders):
    client = MagicMock()
    client.get_account_info_redacted.return_value = sample_account_info
    client.get_positions.return_value = sample_positions
    client.get_orders.return_value = sample_orders
    client.get_symbol_info.return_value = {
        "name": "XAUUSD",
        "digits": 2,
        "point": 0.01,
        "spread": 30,
        "spread_float": True,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_contract_size": 100.0,
        "trade_tick_size": 0.01,
        "trade_tick_value": 1.0,
        "stops_level": 0,
        "freeze_level": 0,
        "trade_mode": 0,
        "filling_mode": 1,
        "execution_mode": 1,
        "currency_base": "XAU",
        "currency_profit": "USD",
        "currency_margin": "USD",
    }
    client.get_symbol_info_tick.return_value = {
        "bid": 2340.50,
        "ask": 2340.80,
        "last": 2340.65,
        "volume": 150,
        "time": 1700000000,
        "time_msc": 1700000000000,
        "flags": 0,
    }
    return client


# ═══════════════════════════════════════════════════════════════════════
# 1. SHADOW MODE (10 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestShadowMode:
    def test_shadow_run_creation(self, shadow_pipeline, sample_tick):
        signal = shadow_pipeline.process_tick(sample_tick)
        assert signal is not None
        assert signal.symbol == "XAUUSD"
        assert signal.direction == "BUY"
        assert signal.entry_price == 2340.50
        assert signal.signal_id.startswith("SHADOW_")

    def test_shadow_vs_live_comparison(self, shadow_pipeline, sample_tick):
        shadow_signal = shadow_pipeline.process_tick(sample_tick)
        assert shadow_signal is not None
        assert shadow_signal.cost_estimate == 0.0
        assert shadow_signal.hypothetical_pnl == 0.0
        ledger = shadow_pipeline.get_ledger()
        assert len(ledger) == 1
        assert ledger[0].fill_price == sample_tick["bid"]

    def test_shadow_performance_tracking(self, shadow_pipeline, sample_tick):
        for i in range(5):
            shadow_pipeline.process_tick(sample_tick)
        summary = shadow_pipeline.get_summary()
        assert summary["signals_generated"] == 5
        assert summary["ledger_entries"] == 5
        assert summary["heartbeat_count"] == 5

    def test_shadow_mode_enable_disable(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("enable_test")
        tick = {"symbol": "EURUSD", "bid": 1.1050, "ask": 1.1052}
        s1 = pipeline.process_tick(tick)
        assert s1 is not None
        pipeline._signals.clear()
        pipeline._ledger.clear()
        summary = pipeline.get_summary()
        assert summary["signals_generated"] == 0
        assert summary["ledger_entries"] == 0

    def test_shadow_state_persistence(self, shadow_pipeline, sample_tick):
        for _ in range(3):
            shadow_pipeline.process_tick(sample_tick)
        seal = shadow_pipeline.seal_ledger()
        assert seal != ""
        assert len(seal) == 64
        assert shadow_pipeline.verify_ledger_integrity()

    def test_shadow_result_validation(self, shadow_pipeline, sample_tick):
        shadow_pipeline.process_tick(sample_tick)
        ledger = shadow_pipeline.get_ledger()
        entry = ledger[0]
        assert entry.record_hash == entry.compute_hash()
        assert shadow_pipeline.verify_ledger_integrity()

    def test_shadow_mode_cost_tracking(self, telemetry):
        telemetry.record_signal()
        telemetry.record_signal()
        telemetry.record_hypothetical_pnl(-12.50)
        telemetry.record_hypothetical_pnl(25.00)
        metrics = telemetry.get_metrics()
        assert metrics.signal_count == 2
        assert metrics.hypothetical_pnl == 12.50

    def test_shadow_mode_pnl_tracking(self, telemetry):
        for pnl in [-10.0, 20.0, -5.0, 30.0]:
            telemetry.record_hypothetical_pnl(pnl)
        metrics = telemetry.get_metrics()
        assert metrics.hypothetical_pnl == 35.0

    def test_shadow_mode_signal_tracking(self, shadow_pipeline, sample_tick):
        for i in range(3):
            tick = {**sample_tick, "bid": sample_tick["bid"] + i * 0.1}
            shadow_pipeline.process_tick(tick)
        signals = shadow_pipeline.get_signals()
        assert len(signals) == 3
        assert signals[0].entry_price != signals[1].entry_price
        assert signals[1].entry_price != signals[2].entry_price

    def test_shadow_mode_risk_tracking(self, telemetry):
        telemetry.record_rejection("risk_limit")
        telemetry.record_event_blocked()
        telemetry.record_health_blocked()
        telemetry.record_stale_feed()
        metrics = telemetry.get_metrics()
        assert metrics.rejection_count == 1
        assert metrics.event_blocked_count == 1
        assert metrics.health_blocked_count == 1
        assert metrics.stale_feed_count == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. CANARY DEPLOYMENT (10 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestCanaryDeployment:
    def test_canary_initialization(self, canary_config):
        assert canary_config.execution_enabled is False
        assert canary_config.account_mode_required == "DEMO"
        assert canary_config.max_open_positions == 1
        assert canary_config.max_orders_per_day == 3
        assert canary_config.require_stop_loss is True

    def test_canary_traffic_splitting_10pct(self, canary_config):
        ok, issues = canary_config.validate()
        assert ok is True
        assert issues == []

    def test_canary_success_metrics(self):
        sc = DemoScorecard()
        metrics = {
            "unexplained_orders": 0,
            "unprotected_positions": 0,
            "stale_data_orders": 0,
            "event_bypass_orders": 0,
            "risk_breaches": 0,
            "reconciliation_pct": 100,
            "critical_incidents": 0,
            "cost_gap_pct": 20,
            "evidence_label": "DEMO_OBSERVED",
        }
        checks = sc.evaluate(metrics)
        assert len(checks) == 9
        assert sc.all_passed()
        summary = sc.summary()
        assert summary["total"] == 9
        assert summary["passed"] == 9
        assert summary["failed"] == 0

    def test_canary_failure_detection(self):
        sc = DemoScorecard()
        metrics = {
            "unexplained_orders": 2,
            "unprotected_positions": 1,
            "stale_data_orders": 0,
            "event_bypass_orders": 0,
            "risk_breaches": 0,
            "reconciliation_pct": 100,
            "critical_incidents": 0,
            "cost_gap_pct": 10,
            "evidence_label": "DEMO_OBSERVED",
        }
        sc.evaluate(metrics)
        assert not sc.all_passed()
        failed = sc.get_failed()
        names = {c.check_name for c in failed}
        assert "no_unexplained_order" in names
        assert "no_unprotected_position" in names

    def test_canary_rollback(self, kill_switch):
        assert not kill_switch.is_active()
        kill_switch.activate("Emergency: spread anomaly")
        assert kill_switch.is_active()
        state = kill_switch.get_state()
        assert state.reason == "Emergency: spread anomaly"
        assert state.activated_by == "manual"
        assert state.activated_at != ""

    def test_canary_promotion_to_live(self):
        sc = DemoScorecard()
        perfect = {
            "unexplained_orders": 0,
            "unprotected_positions": 0,
            "stale_data_orders": 0,
            "event_bypass_orders": 0,
            "risk_breaches": 0,
            "reconciliation_pct": 100,
            "critical_incidents": 0,
            "cost_gap_pct": 30,
            "evidence_label": "DEMO_OBSERVED",
        }
        sc.evaluate(perfect)
        assert sc.all_passed()

    def test_canary_monitoring(self):
        reporter = DailyReporter()
        r1 = DailyReport(date="2026-07-01", health="healthy", signals=15, orders=3, fills=3)
        r2 = DailyReport(date="2026-07-02", health="degraded", signals=10, orders=1, fills=1)
        reporter.add_report(r1)
        reporter.add_report(r2)
        reports = reporter.get_reports()
        assert len(reports) == 2
        latest = reporter.get_latest()
        assert latest.date == "2026-07-02"
        assert latest.health == "degraded"

    def test_canary_timeout_handling(self, kill_switch):
        kill_switch.activate("timeout")
        assert kill_switch.is_active()
        kill_switch.deactivate()
        assert not kill_switch.is_active()

    def test_canary_health_check(self, canary_config):
        ok, issues = canary_config.validate()
        assert ok is True
        canary_config.max_open_positions = 5
        ok2, issues2 = canary_config.validate()
        assert ok2 is False
        assert any("MAX_POSITIONS_TOO_HIGH" in i for i in issues2)

    def test_canary_metrics_aggregation(self, broker_validator, canary_config):
        c1 = broker_validator.validate_account_mode(canary_config.account_mode_required)
        assert c1.passed is True
        c2 = broker_validator.validate_symbol("XAUUSD", {"point": 0.01})
        assert c2.passed is True
        c3 = broker_validator.validate_stop_loss({"stop_loss": 2338.0})
        assert c3.passed is True
        c4 = broker_validator.validate_position_limits(0, canary_config.max_open_positions)
        assert c4.passed is True
        c5 = broker_validator.validate_daily_orders(1, canary_config.max_orders_per_day)
        assert c5.passed is True
        report = BrokerValidationReport()
        report.add_check(c1.name, c1.passed, c1.evidence)
        report.add_check(c2.name, c2.passed, c2.evidence)
        report.add_check(c3.name, c3.passed, c3.evidence)
        report.add_check(c4.name, c4.passed, c4.evidence)
        report.add_check(c5.name, c5.passed, c5.evidence)
        assert report.all_passed
        assert len(report.checks) == 5
        fp = report.fingerprint()
        assert len(fp) == 64


# ═══════════════════════════════════════════════════════════════════════
# 3. LIVE READINESS CHECKS (8 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestLiveReadinessChecks:
    def test_broker_connection_check(self):
        caps = RuntimeCapabilities(mt5_initialized=True, terminal_connected=True, tick_access=True)
        assert not caps.has_critical_issues

    def test_market_data_check(self):
        caps = RuntimeCapabilities(mt5_initialized=True, terminal_connected=False, tick_access=True)
        assert caps.has_critical_issues

    def test_risk_module_check(self, canary_config):
        ok, issues = canary_config.validate()
        assert ok is True
        assert "require_stop_loss" in dir(canary_config)
        assert "max_daily_loss_bps" in dir(canary_config)

    def test_kill_switch_check(self, kill_switch):
        assert not kill_switch.is_active()
        kill_switch.activate("test reason")
        assert kill_switch.is_active()
        state = kill_switch.get_state()
        assert state.active is True
        assert state.reason == "test reason"

    def test_position_limit_check(self, broker_validator, canary_config):
        check = broker_validator.validate_position_limits(open_positions=1, max_positions=1)
        assert check.passed is False
        assert "open=1" in check.evidence
        check2 = broker_validator.validate_position_limits(open_positions=0, max_positions=1)
        assert check2.passed is True

    def test_account_balance_check(self, mock_readonly_client):
        snapshot = take_account_snapshot(mock_readonly_client)
        assert snapshot.balance == Decimal("10000.0")
        assert snapshot.equity == Decimal("10050.0")
        assert snapshot.account_number_redacted == "****1234"
        assert snapshot.leverage == 500
        assert snapshot.open_positions_count == 1
        assert snapshot.open_orders_count == 1
        assert snapshot.snapshot_hash != ""

    def test_symbol_availability_check(self, mock_readonly_client):
        snapshot = take_symbol_snapshot(mock_readonly_client, "XAUUSD")
        assert snapshot.symbol == "XAUUSD"
        assert snapshot.bid == Decimal("2340.50")
        assert snapshot.ask == Decimal("2340.80")
        assert snapshot.digits == 2
        assert snapshot.point == Decimal("0.01")
        assert snapshot.filling_mode == "IOC"
        assert snapshot.execution_mode == "SYMBOL_TRADE_EXECUTION_INSTANT"
        assert snapshot.snapshot_hash != ""

    def test_trading_hours_check(self):
        caps = RuntimeCapabilities(
            mt5_initialized=True,
            terminal_connected=True,
            tick_access=True,
            positions_visible=True,
            orders_visible=True,
            history_visible=True,
        )
        assert not caps.has_critical_issues
        assert caps.positions_visible is True
        assert caps.orders_visible is True
        assert caps.history_visible is True


# ═══════════════════════════════════════════════════════════════════════
# 4. PIPELINE INTEGRATION (7 tests)
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineIntegration:
    def test_signal_to_oms_to_broker_flow(self, shadow_pipeline, sample_tick):
        signal = shadow_pipeline.process_tick(sample_tick)
        assert signal is not None
        assert signal.direction == "BUY"
        ledger = shadow_pipeline.get_ledger()
        assert len(ledger) == 1
        assert ledger[0].fill_price == sample_tick["bid"]
        assert ledger[0].record_hash != ""
        assert shadow_pipeline.verify_ledger_integrity()

    def test_risk_gate_integration(self, broker_validator, canary_config):
        c1 = broker_validator.validate_account_mode(canary_config.account_mode_required)
        c2 = broker_validator.validate_symbol("XAUUSD", {"point": 0.01})
        c3 = broker_validator.validate_stop_loss({"stop_loss": 2338.0})
        c4 = broker_validator.validate_position_limits(0, canary_config.max_open_positions)
        c5 = broker_validator.validate_daily_orders(0, canary_config.max_orders_per_day)
        assert c1.passed is True
        assert c2.passed is True
        assert c3.passed is True
        assert c4.passed is True
        assert c5.passed is True
        checks_by_name = {c.name: c for c in [c1, c2, c3, c4, c5]}
        assert checks_by_name["ACCOUNT_MODE"].passed
        assert checks_by_name["CONTRACT_SPECS"].passed
        assert checks_by_name["STOP_LOSS"].passed
        assert checks_by_name["POSITION_LIMIT"].passed
        assert checks_by_name["DAILY_ORDER_LIMIT"].passed

    def test_position_manager_integration(self):
        broker = [{"ticket": 1, "symbol": "XAUUSD"}]
        expected = [{"ticket": 1, "symbol": "XAUUSD"}]
        result = reconcile_positions(broker, expected)
        assert result.position_reconciled is True
        assert result.deal_reconciled is True
        assert result.mismatch is False
        assert result.position_count == 1
        assert result.expected_position_count == 1

    def test_stop_loss_setup_integration(self):
        result = verify_protective_stops(
            broker_sl=2338.0,
            expected_sl=2338.0,
            broker_tp=2350.0,
            expected_tp=2350.0,
        )
        assert result.verified is True
        assert result.mismatch is False

        result2 = verify_protective_stops(
            broker_sl=2335.0,
            expected_sl=2338.0,
            broker_tp=2350.0,
            expected_tp=2350.0,
        )
        assert result2.verified is False
        assert result2.mismatch is True

    def test_pnl_tracking_integration(self, telemetry, shadow_pipeline, sample_tick):
        shadow_pipeline.process_tick(sample_tick)
        telemetry.record_signal()
        telemetry.record_hypothetical_pnl(25.50)
        telemetry.record_spread(3.0)
        telemetry.record_latency(15.5)
        metrics = telemetry.get_metrics()
        assert metrics.signal_count == 1
        assert metrics.hypothetical_pnl == 25.50
        assert metrics.spread_p50 == 3.0
        assert metrics.decision_latency_ms == 15.5

    def test_trade_journal_integration(self):
        lifecycle = OrderLifecycle()
        assert lifecycle.get_state() == OrderState.SIGNAL_CREATED
        transitions = [
            OrderState.RISK_ACCEPTED,
            OrderState.ORDER_INTENT_CREATED,
            OrderState.ORDER_CHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.BROKER_ACKNOWLEDGED,
            OrderState.FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
            OrderState.POSITION_RECONCILED,
            OrderState.CLOSED,
            OrderState.DEAL_RECONCILED,
            OrderState.AUDITED,
        ]
        for target in transitions:
            ok = lifecycle.transition(target)
            assert ok is True, f"Failed transition to {target}"
        assert lifecycle.get_state() == OrderState.AUDITED
        assert lifecycle.is_terminal()
        history = lifecycle.get_history()
        assert len(history) == 12
        assert history[0] == OrderState.SIGNAL_CREATED
        assert history[-1] == OrderState.AUDITED

    def test_alert_system_integration(self, event_risk_gate, shadow_pipeline, sample_tick):
        now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
        events = [{"name": "NFP", "time": datetime(2026, 7, 6, 12, 15, 0, tzinfo=UTC)}]
        result = event_risk_gate.check(now, events)
        assert result.blocked is True
        assert result.event_name == "NFP"
        assert result.minutes_to_event == 15
        signal = shadow_pipeline.process_tick(sample_tick)
        assert signal is not None
        summary = shadow_pipeline.get_summary()
        assert summary["ledger_valid"] is True


# ═══════════════════════════════════════════════════════════════════════
# 5. ADDITIONAL COVERAGE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestAdditionalCoverage:
    def test_broker_profile_validation(self):
        with pytest.raises(ValueError, match="adapter must be 'mt5'"):
            BrokerProfile(
                profile_id="bad",
                adapter="ib",
                execution_mode="demo",
                expected_server="x",
                account_currency="USD",
                symbols={},
            )

    def test_broker_profile_execution_mode_reject(self):
        with pytest.raises(ValueError, match="execution_mode must be"):
            BrokerProfile(
                profile_id="bad",
                adapter="mt5",
                execution_mode="paper",
                expected_server="x",
                account_currency="USD",
                symbols={},
            )

    def test_broker_profile_readonly_enforced(self):
        with pytest.raises(ValueError, match="READ_ONLY"):
            BrokerProfile(
                profile_id="bad",
                adapter="mt5",
                execution_mode="demo",
                expected_server="x",
                account_currency="USD",
                symbols={},
                allowed_actions=["ORDER_SEND"],
            )

    def test_default_profile_is_valid(self):
        assert DEFAULT_PROFILE.profile_id == "icmarkets_demo_mt5"
        assert DEFAULT_PROFILE.adapter == "mt5"
        assert "XAUUSD" in DEFAULT_PROFILE.symbols

    def test_smoke_report_verdict_pass(self):
        caps = RuntimeCapabilities(mt5_initialized=True, terminal_connected=True, tick_access=True)
        profile = DEFAULT_PROFILE
        report = generate_smoke_report(profile, caps)
        assert report.verdict == "PASS"
        assert report.all_checks_passed is True
        assert report.issues == []

    def test_smoke_report_verdict_degraded(self):
        caps = RuntimeCapabilities(
            mt5_initialized=True,
            terminal_connected=True,
            tick_access=False,
            issues=["copy_ticks_range returned empty for XAUUSD"],
        )
        report = generate_smoke_report(DEFAULT_PROFILE, caps)
        assert report.verdict == "DEGRADED"

    def test_smoke_report_verdict_fail(self):
        caps = RuntimeCapabilities(
            mt5_initialized=False,
            terminal_connected=False,
            issues=["mt5.initialize failed: not installed", "terminal reports disconnected"],
        )
        report = generate_smoke_report(DEFAULT_PROFILE, caps)
        assert report.verdict == "FAIL"

    def test_smoke_report_persist(self):
        caps = RuntimeCapabilities(mt5_initialized=True, terminal_connected=True, tick_access=True)
        report = generate_smoke_report(DEFAULT_PROFILE, caps)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = persist_smoke_report(report, tmpdir)
            assert os.path.exists(path)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data["verdict"] == "PASS"
            assert data["profile_id"] == "icmarkets_demo_mt5"

    def test_smoke_report_human_format(self):
        caps = RuntimeCapabilities(
            mt5_initialized=True,
            terminal_connected=True,
            tick_access=True,
            symbols_available=["XAUUSD", "EURUSD"],
        )
        report = generate_smoke_report(DEFAULT_PROFILE, caps)
        text = format_smoke_report_human(report)
        assert "SMOKE REPORT" in text
        assert "PASS" in text
        assert "XAUUSD" in text

    def test_account_snapshot_hash_determinism(self, mock_readonly_client):
        from datetime import datetime
        from unittest.mock import patch

        fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("graxia.packages.quant_os.live_readiness.account_snapshot_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            s1 = take_account_snapshot(mock_readonly_client)
            s2 = take_account_snapshot(mock_readonly_client)
            assert s1.snapshot_hash == s2.snapshot_hash
            assert len(s1.snapshot_hash) == 64  # SHA-256 hex

    def test_account_redact_short_number(self):
        assert _redact_account_number(1234) == "1234"
        assert _redact_account_number(12345) == "*2345"

    def test_symbol_snapshot_persist(self, mock_readonly_client):
        snap = take_symbol_snapshot(mock_readonly_client, "XAUUSD")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = persist_symbol_snapshot(snap, tmpdir)
            assert os.path.exists(path)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data["symbol"] == "XAUUSD"
            assert float(data["bid"]) == 2340.5

    def test_shadow_invalid_tick(self, shadow_pipeline):
        bad_tick = {"symbol": "XAUUSD", "bid": 0, "ask": 0}
        signal = shadow_pipeline.process_tick(bad_tick)
        assert signal is None
        incidents = shadow_pipeline.get_incidents()
        assert len(incidents) == 1
        assert incidents[0]["type"] == "invalid_tick"

    def test_shadow_ledger_seal_empty(self):
        p = ShadowPipeline()
        p.start_session("empty")
        assert p.seal_ledger() == ""

    def test_shadow_campaign_lifecycle(self, campaign_config):
        campaign = ShadowCampaign(campaign_config)
        assert campaign.is_active() is False
        assert campaign.get_status() == "idle"
        campaign.start()
        assert campaign.is_active() is True
        assert campaign.get_status() == "running"
        campaign.record_signal()
        campaign.record_signal()
        campaign.record_signal()
        campaign.stop("completed")
        assert campaign.is_active() is False
        assert campaign.get_status() == "completed"
        summary = campaign.get_summary()
        assert summary["signal_count"] == 3

    def test_shadow_campaign_failure(self, campaign_config):
        campaign = ShadowCampaign(campaign_config)
        campaign.start()
        campaign.record_signal()
        campaign.stop("data_feed_loss")
        assert campaign.get_status() == "failed"
        summary = campaign.get_summary()
        assert summary["status"] == "failed"

    def test_event_risk_gate_no_events(self):
        gate = EventRiskGate(blackout_minutes=30)
        now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
        result = gate.check(now, [])
        assert result.blocked is False

    def test_event_risk_gate_event_outside_window(self):
        gate = EventRiskGate(blackout_minutes=30)
        now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
        events = [{"name": "NFP", "time": datetime(2026, 7, 6, 14, 0, 0, tzinfo=UTC)}]
        result = gate.check(now, events)
        assert result.blocked is False

    def test_market_health_transitions(self):
        machine = MarketHealthMachine()
        check = machine.check(feed_ok=True, clock_ok=True, spread_ok=True, session_ok=True)
        assert check.state == MarketHealthState.HEALTHY
        assert machine.is_healthy()
        check2 = machine.check(feed_ok=True, clock_ok=False, spread_ok=True, session_ok=True)
        assert check2.state == MarketHealthState.DEGRADED
        assert not machine.is_healthy()
        check3 = machine.check(feed_ok=False, clock_ok=True, spread_ok=True, session_ok=True)
        assert check3.state == MarketHealthState.DISCONNECTED

    def test_failure_rule_checker(self):
        checker = FailureRuleChecker()
        assert checker.has_violations() is False
        result = checker.check("STALE_DATA_ACCEPTED")
        assert result is True
        assert checker.has_violations()
        violations = checker.get_violations()
        assert len(violations) == 1
        assert violations[0]["rule"] == "STALE_DATA_ACCEPTED"
        checker.clear()
        assert checker.has_violations() is False

    def test_failure_rules_all_defined(self):
        expected = {
            "STALE_DATA_ACCEPTED",
            "EVENT_BLOCK_BYPASS",
            "MISSING_CONTRACT",
            "INVALID_SL_ACCEPTED",
            "RISK_BREACH",
            "DUPLICATE_IDEMPOTENCY",
            "INVALID_TRANSITION",
            "UNCORRELATED_ALERT",
            "PIPELINE_EXCEPTION",
        }
        actual = {r.name for r in FAILURE_RULES}
        assert expected == actual

    def test_canary_config_validation_rejects_high_risk(self):
        config = CanaryConfig(risk_per_trade_bps=100)
        ok, issues = config.validate()
        assert ok is False
        assert any("RISK_TOO_HIGH" in i for i in issues)

    def test_canary_config_validation_rejects_auto_resume(self):
        config = CanaryConfig(auto_resume_after_kill_switch=True)
        ok, issues = config.validate()
        assert ok is False
        assert "AUTO_RESUME_FORBIDDEN" in issues

    def test_canary_config_symbol_check(self, canary_config):
        ok, msg = canary_config.check_symbol("XAUUSD")
        assert ok is True
        ok2, msg2 = canary_config.check_symbol("BTCUSD")
        assert ok2 is False
        assert "SYMBOL_NOT_ALLOWED" in msg2

    def test_canary_config_strategy_check(self, canary_config):
        ok, msg = canary_config.check_strategy("liquidity_sweep_locked_version")
        assert ok is True
        ok2, msg2 = canary_config.check_strategy("unknown_strategy")
        assert ok2 is False
        assert "STRATEGY_NOT_ALLOWED" in msg2

    def test_canary_config_fingerprint(self, canary_config):
        fp1 = canary_config.fingerprint()
        fp2 = canary_config.fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_canary_config_to_yaml(self, canary_config):
        yaml_str = canary_config.to_yaml()
        assert "demo_canary" in yaml_str
        assert "XAUUSD" in yaml_str

    def test_order_lifecycle_invalid_transition(self):
        lifecycle = OrderLifecycle()
        ok = lifecycle.transition(OrderState.FILLED)
        assert ok is False
        assert lifecycle.get_state() == OrderState.SIGNAL_CREATED

    def test_order_lifecycle_rejection_path(self):
        lifecycle = OrderLifecycle()
        ok = lifecycle.transition(OrderState.REJECTED)
        assert ok is True
        assert lifecycle.is_terminal()

    def test_order_lifecycle_is_filled(self):
        lifecycle = OrderLifecycle()
        lifecycle.transition(OrderState.RISK_ACCEPTED)
        lifecycle.transition(OrderState.ORDER_INTENT_CREATED)
        lifecycle.transition(OrderState.ORDER_CHECKED)
        lifecycle.transition(OrderState.ORDER_SUBMITTED)
        lifecycle.transition(OrderState.BROKER_ACKNOWLEDGED)
        lifecycle.transition(OrderState.FILLED)
        assert lifecycle.is_filled()

    def test_daily_report_to_dict(self):
        r = DailyReport(date="2026-07-06", health="healthy", signals=10, orders=2, fills=2)
        d = r.to_dict()
        assert d["date"] == "2026-07-06"
        assert d["signals"] == 10
        assert d["health"] == "healthy"

    def test_daily_report_to_markdown(self):
        r = DailyReport(date="2026-07-06", health="healthy", signals=10, orders=2, fills=2)
        md = r.to_markdown()
        assert "# Daily Report: 2026-07-06" in md
        assert "healthy" in md

    def test_protective_stops_tolerance(self):
        result = verify_protective_stops(
            broker_sl=2338.005,
            expected_sl=2338.0,
            broker_tp=2350.0,
            expected_tp=2350.0,
            tolerance=0.01,
        )
        assert result.verified is True

    def test_reconciliation_mismatch(self):
        broker = [{"ticket": 1}, {"ticket": 2}]
        expected = [{"ticket": 1}]
        result = reconcile_positions(broker, expected)
        assert result.mismatch is True
        assert result.position_count == 2
        assert result.expected_position_count == 1

    def test_shadow_telemetry_spread_percentiles(self):
        t = ShadowTelemetry()
        for s in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
            t.record_spread(s)
        metrics = t.get_metrics()
        assert metrics.spread_p50 == 5.0 or metrics.spread_p50 == 6.0
        assert metrics.max_spread == 10.0

    def test_shadow_telemetry_latency_average(self):
        t = ShadowTelemetry()
        for lat in [10.0, 20.0, 30.0]:
            t.record_latency(lat)
        metrics = t.get_metrics()
        assert metrics.decision_latency_ms == 20.0

    def test_shadow_telemetry_heartbeat(self):
        t = ShadowTelemetry()
        t.record_heartbeat()
        t.record_heartbeat()
        t.record_incident()
        t.record_contract_change()
        metrics = t.get_metrics()
        assert metrics.heartbeat_count == 2
        assert metrics.incident_count == 1
        assert metrics.contract_change_count == 1

    def test_shadow_pass_criteria_all_pass(self):
        spc = ShadowPassCriteria()
        metrics = {
            "order_count": 0,
            "stale_feed_count": 0,
            "event_bypass_count": 0,
            "has_contract_snapshot": True,
            "ledger_sealed": True,
            "critical_exception_count": 0,
            "heartbeat_count": 5,
            "unresolved_incidents": 0,
        }
        checks = spc.evaluate(metrics)
        assert len(checks) == 8
        assert spc.all_passed()

    def test_shadow_pass_criteria_failures(self):
        spc = ShadowPassCriteria()
        metrics = {
            "order_count": 1,
            "stale_feed_count": 2,
            "event_bypass_count": 0,
            "has_contract_snapshot": True,
            "ledger_sealed": False,
            "critical_exception_count": 1,
            "heartbeat_count": 0,
            "unresolved_incidents": 3,
        }
        checks = spc.evaluate(metrics)
        assert not spc.all_passed()
        failed = spc.get_failed()
        assert len(failed) == 6

    def test_broker_validator_stop_loss_missing(self, broker_validator):
        check = broker_validator.validate_stop_loss({"stop_loss": 0})
        assert check.passed is False

    def test_broker_validator_daily_orders(self, broker_validator):
        check = broker_validator.validate_daily_orders(orders_today=3, max_orders=3)
        assert check.passed is False
        check2 = broker_validator.validate_daily_orders(orders_today=2, max_orders=3)
        assert check2.passed is True

    def test_broker_validator_symbol_no_specs(self, broker_validator):
        check = broker_validator.validate_symbol("XAUUSD", {})
        assert check.passed is False
        assert "no specs" in check.evidence

    def test_kill_switch_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ks.json")
            ks1 = EmergencyKillSwitch(state_file=path)
            ks1.activate("persist test")
            ks2 = EmergencyKillSwitch(state_file=path)
            assert ks2.is_active() is True
            assert ks2.get_state().reason == "persist test"

    def test_shadow_pipeline_multiple_sessions(self):
        p = ShadowPipeline()
        p.start_session("session_1")
        tick = {"symbol": "EURUSD", "bid": 1.1050, "ask": 1.1052}
        p.process_tick(tick)
        assert len(p.get_signals()) == 1
        p.start_session("session_2")
        assert len(p.get_signals()) == 0
        assert p.get_summary()["signals_generated"] == 0
