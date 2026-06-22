import pytest
import json
from datetime import datetime
from shadow.pipeline import (
    ShadowPipeline, ShadowSignal, ShadowSession, ShadowSignalOutcome
)
from shadow.failure_rules import FailureRuleChecker, FAILURE_RULES
from shadow.telemetry import ShadowTelemetry, TelemetrySummary


def _make_signal(outcome=None, event_state="CLEAR", health_state="HEALTHY", sl=1.0):
    return ShadowSignal(
        signal_id="SIG-001",
        timestamp=datetime(2025, 1, 15, 14, 0),
        symbol="XAUUSD",
        direction="BUY",
        entry_price=2350.0,
        stop_loss=sl,
        take_profit=2370.0,
        outcome=outcome or ShadowSignalOutcome.ACCEPTED,
        event_risk_state=event_state,
        market_health_state=health_state,
        sized_volume=0.1,
        hypothetical_fill_price=2350.5,
    )


class TestShadowPipeline:
    def test_start_session(self):
        pipeline = ShadowPipeline()
        session = pipeline.start_session("SES-001")
        assert session.session_id == "SES-001"
        assert session.ended_at is None

    def test_end_session(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        pipeline.end_session()
        assert pipeline._current_session is None

    def test_process_signal_accepted(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        signal = _make_signal()
        result = pipeline.process_signal(signal)
        assert result.outcome == ShadowSignalOutcome.ACCEPTED

    def test_process_signal_event_block(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        signal = _make_signal(event_state="EVENT_BLOCK")
        result = pipeline.process_signal(signal)
        assert result.outcome == ShadowSignalOutcome.REJECTED_EVENT_BLOCK

    def test_process_signal_market_unhealthy(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        signal = _make_signal(health_state="DISCONNECTED")
        result = pipeline.process_signal(signal)
        assert result.outcome == ShadowSignalOutcome.REJECTED_MARKET_HEALTH

    def test_process_signal_invalid_sl(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        signal = _make_signal(sl=0)
        result = pipeline.process_signal(signal)
        assert result.outcome == ShadowSignalOutcome.REJECTED_INVALID_SL

    def test_no_session_raises(self):
        pipeline = ShadowPipeline()
        signal = _make_signal()
        with pytest.raises(ValueError):
            pipeline.process_signal(signal)

    def test_session_summary(self):
        pipeline = ShadowPipeline()
        session = pipeline.start_session("SES-001")
        pipeline.process_signal(_make_signal())
        pipeline.process_signal(_make_signal(event_state="EVENT_BLOCK"))
        summary = session.summary()
        assert summary["total_signals"] == 2
        assert summary["accepted"] == 1

    def test_session_summary_empty(self):
        pipeline = ShadowPipeline()
        session = pipeline.start_session("SES-001")
        summary = session.summary()
        assert summary["total_signals"] == 0
        assert summary["accepted"] == 0
        assert summary["rejected"] == 0
        assert summary["acceptance_rate"] == 0

    def test_session_summary_all_rejected(self):
        pipeline = ShadowPipeline()
        session = pipeline.start_session("SES-001")
        pipeline.process_signal(_make_signal(event_state="EVENT_BLOCK"))
        pipeline.process_signal(_make_signal(health_state="DISCONNECTED"))
        pipeline.process_signal(_make_signal(sl=0))
        summary = session.summary()
        assert summary["total_signals"] == 3
        assert summary["accepted"] == 0
        assert summary["rejected"] == 3
        assert summary["acceptance_rate"] == 0

    def test_get_session(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        session = pipeline.get_session("SES-001")
        assert session is not None
        assert session.session_id == "SES-001"

    def test_get_session_not_found(self):
        pipeline = ShadowPipeline()
        session = pipeline.get_session("NONEXISTENT")
        assert session is None

    def test_list_sessions(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        pipeline.start_session("SES-002")
        sessions = pipeline.list_sessions()
        assert len(sessions) == 2

    def test_multiple_signals_accepted(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        for i in range(5):
            signal = _make_signal()
            signal.signal_id = f"SIG-{i:03d}"
            result = pipeline.process_signal(signal)
            assert result.outcome == ShadowSignalOutcome.ACCEPTED

    def test_signal_event_block_with_rejection_reason(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        signal = _make_signal(event_state="NFP")
        result = pipeline.process_signal(signal)
        assert result.outcome == ShadowSignalOutcome.REJECTED_EVENT_BLOCK
        assert "EVENT_BLOCK:NFP" in result.rejection_reason

    def test_signal_market_health_with_rejection_reason(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("SES-001")
        signal = _make_signal(health_state="LATE_DATA")
        result = pipeline.process_signal(signal)
        assert result.outcome == ShadowSignalOutcome.REJECTED_MARKET_HEALTH
        assert "MARKET_UNHEALTHY:LATE_DATA" in result.rejection_reason

    def test_session_export(self):
        pipeline = ShadowPipeline()
        session = pipeline.start_session("SES-001")
        session.add_signal(_make_signal())
        exported = session.export()
        data = json.loads(exported)
        assert data["session_id"] == "SES-001"
        assert len(data["signals"]) == 1


class TestShadowSignal:
    def test_fingerprint(self):
        s = _make_signal()
        f = s.fingerprint()
        assert len(f) == 64

    def test_to_dict(self):
        s = _make_signal()
        d = s.to_dict()
        assert "signal_id" in d
        assert "outcome" in d

    def test_fingerprint_deterministic(self):
        s = _make_signal()
        assert s.fingerprint() == s.fingerprint()

    def test_fingerprint_unique_per_signal(self):
        s1 = _make_signal()
        s1.signal_id = "SIG-001"
        s2 = _make_signal()
        s2.signal_id = "SIG-002"
        assert s1.fingerprint() != s2.fingerprint()

    def test_to_dict_all_fields(self):
        s = _make_signal()
        d = s.to_dict()
        assert d["signal_id"] == "SIG-001"
        assert d["symbol"] == "XAUUSD"
        assert d["direction"] == "BUY"
        assert d["entry_price"] == 2350.0
        assert d["stop_loss"] == 1.0
        assert d["take_profit"] == 2370.0
        assert d["event_risk_state"] == "CLEAR"
        assert d["market_health_state"] == "HEALTHY"
        assert d["sized_volume"] == 0.1
        assert d["hypothetical_fill_price"] == 2350.5

    def test_signal_outcome_values(self):
        assert ShadowSignalOutcome.ACCEPTED.value == "accepted"
        assert ShadowSignalOutcome.REJECTED_EVENT_BLOCK.value == "rejected_event_block"
        assert ShadowSignalOutcome.REJECTED_MARKET_HEALTH.value == "rejected_market_health"
        assert ShadowSignalOutcome.REJECTED_RISK.value == "rejected_risk"
        assert ShadowSignalOutcome.REJECTED_DATA_STALE.value == "rejected_data_stale"
        assert ShadowSignalOutcome.REJECTED_INVALID_SL.value == "rejected_invalid_sl"
        assert ShadowSignalOutcome.REJECTED_DUPLICATE.value == "rejected_duplicate"

    def test_rejection_reason_default_empty(self):
        s = _make_signal()
        assert s.rejection_reason == ""


class TestFailureRules:
    def test_rules_exist(self):
        assert len(FAILURE_RULES) >= 9

    def test_checker_detects_violation(self):
        checker = FailureRuleChecker()
        found = checker.check("STALE_DATA_ACCEPTED")
        assert found is True
        assert checker.has_violations() is True

    def test_checker_clear(self):
        checker = FailureRuleChecker()
        checker.check("STALE_DATA_ACCEPTED")
        checker.clear()
        assert checker.has_violations() is False

    def test_checker_unknown_rule(self):
        checker = FailureRuleChecker()
        found = checker.check("NONEXISTENT_RULE")
        assert found is False
        assert checker.has_violations() is False

    def test_checker_records_all_violations(self):
        checker = FailureRuleChecker()
        for rule in FAILURE_RULES:
            checker.check(rule.name)
        violations = checker.get_violations()
        assert len(violations) == len(FAILURE_RULES)

    def test_checker_with_context(self):
        checker = FailureRuleChecker()
        context = {"symbol": "XAUUSD", "reason": "test"}
        checker.check("RISK_BREACH", context=context)
        violations = checker.get_violations()
        assert len(violations) == 1
        assert violations[0]["context"]["symbol"] == "XAUUSD"

    def test_failure_rule_blocks_progression(self):
        for rule in FAILURE_RULES:
            assert rule.blocks_progression is True

    def test_failure_rule_names(self):
        expected_names = {
            "STALE_DATA_ACCEPTED", "EVENT_BLOCK_BYPASS", "MISSING_CONTRACT",
            "INVALID_SL_ACCEPTED", "RISK_BREACH", "DUPLICATE_IDEMPOTENCY",
            "INVALID_TRANSITION", "UNCORRELATED_ALERT", "PIPELINE_EXCEPTION",
        }
        actual_names = {r.name for r in FAILURE_RULES}
        assert expected_names == actual_names

    def test_checker_no_violations_initially(self):
        checker = FailureRuleChecker()
        assert checker.has_violations() is False
        assert checker.get_violations() == []


class TestShadowTelemetry:
    def test_start(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        assert len(tel.list_events()) == 1

    def test_record_signal(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        tel.record_signal_created("SES-001", "SIG-001")
        tel.record_signal_accepted("SES-001", "SIG-001")
        summary = tel.get_summary("SES-001")
        assert summary.signals_created == 1
        assert summary.signals_accepted == 1

    def test_record_rejection(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        tel.record_signal_rejected("SES-001", "SIG-001", "EVENT_BLOCK")
        summary = tel.get_summary("SES-001")
        assert summary.signals_rejected == 1

    def test_export_json(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        j = tel.export_json("SES-001")
        assert "session_started" in j

    def test_pipeline_error(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        tel.record_pipeline_error("SES-001", "Connection timeout")
        summary = tel.get_summary("SES-001")
        assert summary.pipeline_errors == 1

    def test_summary_counts(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        tel.record_signal_created("SES-001", "SIG-001")
        tel.record_signal_created("SES-001", "SIG-002")
        tel.record_signal_accepted("SES-001", "SIG-001")
        tel.record_signal_rejected("SES-001", "SIG-002", "EVENT_BLOCK")
        summary = tel.get_summary("SES-001")
        assert summary.total_events == 5
        assert summary.signals_created == 2
        assert summary.signals_accepted == 1
        assert summary.signals_rejected == 1

    def test_summary_session_filter(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        tel.record_signal_created("SES-001", "SIG-001")
        tel.record_signal_created("SES-002", "SIG-002")
        summary_1 = tel.get_summary("SES-001")
        summary_2 = tel.get_summary("SES-002")
        assert summary_1.signals_created == 1
        assert summary_2.signals_created == 1

    def test_export_json_format(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        tel.record_signal_created("SES-001", "SIG-001")
        j = tel.export_json("SES-001")
        data = json.loads(j)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_events_returns_copy(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        events = tel.list_events()
        events.clear()
        assert len(tel.list_events()) == 1

    def test_summary_to_dict(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        summary = tel.get_summary("SES-001")
        d = summary.to_dict()
        assert d["session_id"] == "SES-001"
        assert d["total_events"] == 1
        assert d["signals_created"] == 0
        assert d["signals_accepted"] == 0
        assert d["signals_rejected"] == 0
        assert d["pipeline_errors"] == 0

    def test_event_to_dict(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        events = tel.list_events()
        d = events[0].to_dict()
        assert d["event_type"] == "session_started"
        assert d["session_id"] == "SES-001"
        assert "timestamp" in d

    def test_uptime_seconds(self):
        tel = ShadowTelemetry()
        tel.start("SES-001")
        summary = tel.get_summary("SES-001")
        assert summary.uptime_seconds >= 0
