"""Tests for the synthetic test runner."""
from app.beta.synthetic_tester.runner import SyntheticTestRunner, SyntheticRunResult
from app.beta.synthetic_tester.personas import list_personas


def test_runner_initializes():
    """Runner should initialize with default state."""
    runner = SyntheticTestRunner(run_id="rt-001")
    assert runner.run_id == "rt-001"
    assert runner.backend_running is False
    assert runner.frontend_running is False
    assert len(runner.results) == 0


def test_runner_initializes_with_runtime():
    """Runner should accept runtime flags."""
    runner = SyntheticTestRunner(run_id="rt-002", backend_running=True, frontend_running=True)
    assert runner.backend_running is True
    assert runner.frontend_running is True


def test_runner_run_persona_returns_result():
    """Running a persona should return a SyntheticRunResult."""
    runner = SyntheticTestRunner(run_id="rt-003")
    result = runner.run_persona_tasks("P01")
    assert isinstance(result, SyntheticRunResult)
    assert result.evidence.persona_id == "P01"
    assert result.verdict in ("PASS", "PARTIAL", "FAIL", "NOT_TESTED")


def test_runner_run_unknown_persona():
    """Running an unknown persona should return NOT_TESTED."""
    runner = SyntheticTestRunner(run_id="rt-004")
    result = runner.run_persona_tasks("P99")
    assert result.verdict == "NOT_TESTED"


def test_runner_run_all_personas():
    """Running all personas should produce results for each."""
    runner = SyntheticTestRunner(run_id="rt-005")
    results = runner.run_all_personas()
    personas = list_personas()
    assert len(results) > 0
    persona_results = [r for r in results if r.evidence.persona_id and r.evidence.task_id is None]
    assert len(persona_results) == len(personas)


def test_runner_final_report():
    """Final report should return summary dict."""
    runner = SyntheticTestRunner(run_id="rt-006")
    runner.run_all_personas()
    report = runner.final_report()
    assert report["run_id"] == "rt-006"
    assert report["backend_running"] is False
    assert report["frontend_running"] is False
    assert report["browser_used"] is False
    assert report["personas_run"] > 0
    assert "confidence" in report
    assert "persona_verdicts" in report
