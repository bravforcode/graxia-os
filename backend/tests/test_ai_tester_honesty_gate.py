"""Tests for AI tester honesty gate."""
from app.beta.synthetic_tester.honesty_gate import (
    check_h001_browser_claim,
    check_h002_api_claim,
    check_h003_workflow_claim,
    check_h004_synthetic_claim,
    check_h005_runtime_claim,
    check_h006_correlation_ids,
    check_h007_production_ready,
    check_h008_live_providers,
    check_h009_approval_bypass,
    check_h010_raw_token_leak,
    run_honesty_gate,
    Verdict,
    HonestyGateResult,
)
from app.beta.synthetic_tester.evidence import make_evidence, SyntheticEvidence


def _make_ev(test_type="STATIC_REVIEW", **kwargs) -> SyntheticEvidence:
    ev = make_evidence(run_id="test-hg", test_type=test_type, role="Test")
    for k, v in kwargs.items():
        setattr(ev, k, v)
    return ev


class TestH001BrowserClaim:
    def test_no_browser_claims_correctly(self):
        ev = _make_ev(browser_used=False)
        result = check_h001_browser_claim(ev)
        assert result.rule_id == "H001"

    def test_browser_used_passes(self):
        ev = _make_ev(test_type="BROWSER_E2E", browser_used=True)
        result = check_h001_browser_claim(ev)
        assert result.verdict == Verdict.PASS


class TestH002ApiClaim:
    def test_no_api_calls_warns(self):
        ev = _make_ev(test_type="API_RUNTIME")
        result = check_h002_api_claim(ev)
        assert result.rule_id == "H002"

    def test_api_calls_present_passes(self):
        ev = _make_ev(test_type="API_RUNTIME")
        ev.add_api_call(method="GET", path="/health", status=200)
        result = check_h002_api_claim(ev)
        assert result.verdict == Verdict.PASS


class TestH003WorkflowClaim:
    def test_no_workflow_runs_warns(self):
        ev = _make_ev()
        result = check_h003_workflow_claim(ev)
        assert result.verdict == Verdict.WARN

    def test_workflow_runs_present_passes(self):
        ev = _make_ev()
        ev.add_workflow_run(name="test", mode="draft", result="PASS")
        result = check_h003_workflow_claim(ev)
        assert result.verdict == Verdict.PASS


class TestH004SyntheticClaim:
    def test_synthetic_passes(self):
        ev = _make_ev(test_type="SYNTHETIC_ROLEPLAY")
        result = check_h004_synthetic_claim(ev)
        assert result.verdict == Verdict.PASS
        assert "synthetic" in result.message.lower()

    def test_non_synthetic_passes(self):
        ev = _make_ev(test_type="REAL_HUMAN")
        result = check_h004_synthetic_claim(ev)
        assert result.verdict == Verdict.PASS


class TestH005RuntimeClaim:
    def test_backend_not_running_passes_when_not_api(self):
        ev = _make_ev(test_type="STATIC_REVIEW", backend_running=False)
        result = check_h005_runtime_claim(ev)
        assert result.verdict == Verdict.PASS

    def test_backend_running_passes(self):
        ev = _make_ev(test_type="API_RUNTIME", backend_running=True)
        result = check_h005_runtime_claim(ev)
        assert result.verdict == Verdict.PASS


class TestH006CorrelationIds:
    def test_missing_ids_warns(self):
        ev = _make_ev()
        result = check_h006_correlation_ids(ev)
        assert result.verdict == Verdict.WARN

    def test_ids_present_passes(self):
        ev = _make_ev()
        ev.request_ids.append("req-001")
        ev.correlation_ids.append("corr-001")
        result = check_h006_correlation_ids(ev)
        assert result.verdict == Verdict.PASS


class TestH007ProductionReady:
    def test_production_false_passes(self):
        ev = _make_ev(production_ready=False)
        result = check_h007_production_ready(ev)
        assert result.verdict == Verdict.PASS

    def test_production_true_fails(self):
        ev = _make_ev(production_ready=True)
        result = check_h007_production_ready(ev)
        assert result.verdict == Verdict.FAIL


class TestH008LiveProviders:
    def test_all_false_passes(self):
        ev = _make_ev(live_provider_flags={"LIVE": False})
        result = check_h008_live_providers(ev)
        assert result.verdict == Verdict.PASS

    def test_live_true_fails(self):
        ev = _make_ev(live_provider_flags={"LIVE": True})
        result = check_h008_live_providers(ev)
        assert result.verdict == Verdict.FAIL


class TestH009ApprovalBypass:
    def test_no_bypass_passes(self):
        ev = _make_ev()
        ev.add_workflow_run(name="test", mode="approval", result="PASS")
        result = check_h009_approval_bypass(ev)
        assert result.verdict == Verdict.PASS

    def test_bypass_detected_fails(self):
        ev = _make_ev()
        ev.add_workflow_run(name="test", mode="draft", result="auto_send")
        result = check_h009_approval_bypass(ev)
        assert result.verdict == Verdict.FAIL


class TestH010RawTokenLeak:
    def test_clean_output_passes(self):
        ev = _make_ev(output_summary="All tests passed safely")
        result = check_h010_raw_token_leak(ev)
        assert result.verdict == Verdict.PASS

    def test_token_pattern_detected_fails(self):
        ev = _make_ev(output_summary="Token: sk-abc123def")
        result = check_h010_raw_token_leak(ev)
        assert result.verdict == Verdict.FAIL


class TestFullGate:
    def test_honesty_gate_runs_all_rules(self):
        ev = _make_ev()
        result = run_honesty_gate(ev)
        assert len(result.checks) == 12

    def test_honesty_gate_no_hard_fail_for_clean_evidence(self):
        ev = _make_ev(
            test_type="STATIC_REVIEW",
            browser_used=False,
            backend_running=False,
            production_ready=False,
            live_provider_flags={"LIVE": False},
            output_summary="Clean test output",
        )
        ev.request_ids.append("req-001")
        ev.correlation_ids.append("corr-001")
        result = run_honesty_gate(ev)
        assert not result.hard_fail, f"Unexpected hard fail: {result.summary()}"

    def test_production_false_hard_fail(self):
        ev = _make_ev(production_ready=True)
        result = run_honesty_gate(ev)
        assert result.hard_fail
