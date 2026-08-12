"""Tests for synthetic tester task runner."""
from app.beta.synthetic_tester.tasks import get_task, list_tasks, list_tasks_by_category, list_tasks_by_mode, TASKS
from app.beta.synthetic_tester.runner import SyntheticTestRunner


def test_all_30_tasks_defined():
    """Should have exactly 30 tasks."""
    assert len(TASKS) == 30


def test_each_task_has_required_fields():
    """Each task must have all required fields populated."""
    for tid, t in TASKS.items():
        assert t.task_id == tid
        assert t.title
        assert t.category
        assert t.required_mode
        assert isinstance(t.persona_ids, list)
        assert len(t.persona_ids) > 0
        assert isinstance(t.steps, list)
        assert len(t.steps) > 0
        assert t.expected_result
        assert isinstance(t.evidence_required, list)
        assert isinstance(t.hard_fail_conditions, list)
        assert isinstance(t.confidence_impact, dict)


def test_get_task_returns_correct_task():
    """get_task should return the right task by ID."""
    t = get_task("T001")
    assert t is not None
    assert t.title == "Understand Beta Limits"


def test_get_task_returns_none_for_missing():
    """get_task should return None for unknown ID."""
    assert get_task("T999") is None


def test_list_tasks_returns_all():
    """list_tasks should return all 30 tasks."""
    tasks = list_tasks()
    assert len(tasks) == 30


def test_list_tasks_by_category():
    """list_tasks_by_category should filter correctly."""
    adversarial = list_tasks_by_category("ADVERSARIAL")
    assert len(adversarial) >= 10  # Should have many adversarial tasks


def test_list_tasks_by_mode():
    """list_tasks_by_mode should filter correctly."""
    static = list_tasks_by_mode("STATIC_REVIEW")
    assert len(static) > 0


def test_task_id_uniqueness():
    """All task IDs must be unique."""
    ids = [t.task_id for t in TASKS.values()]
    assert len(ids) == len(set(ids))


def test_task_categories_covered():
    """Should have tasks in all expected categories."""
    categories = {t.category for t in TASKS.values()}
    expected = {"ONBOARDING", "SAFETY_UNDERSTANDING", "READINESS", "WORKFLOW", "APPROVAL", "FEEDBACK", "ADVERSARIAL", "ACCESSIBILITY", "OPERATOR"}
    for exp in expected:
        assert exp in categories, f"Missing category: {exp}"


def test_runner_creates_results():
    """Runner should produce results for a persona."""
    runner = SyntheticTestRunner(run_id="phase22-test")
    result = runner.run_persona_tasks("P01")
    assert result is not None
    assert result.verdict in ("PASS", "PARTIAL", "NOT_TESTED")


def test_runner_handles_unknown_persona():
    """Runner should handle unknown persona gracefully."""
    runner = SyntheticTestRunner(run_id="phase22-test")
    result = runner.run_persona_tasks("P99")
    assert result.verdict == "NOT_TESTED"


def test_runner_produces_final_report():
    """Runner should produce a final report."""
    runner = SyntheticTestRunner(run_id="phase22-final")
    runner.run_all_personas()
    report = runner.final_report()
    assert report["run_id"] == "phase22-final"
    assert report["personas_run"] == 12
    assert callable(report["confidence"].summary)
