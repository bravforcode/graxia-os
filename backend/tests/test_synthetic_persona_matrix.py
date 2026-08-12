"""Tests for synthetic persona matrix."""
from app.beta.synthetic_tester.personas import (
    get_persona,
    list_personas,
    PERSONAS,
)


def test_all_12_personas_defined():
    """Should have exactly 12 personas."""
    assert len(PERSONAS) == 12


def test_each_persona_has_required_fields():
    """Each persona must have all required fields populated."""
    for pid, p in PERSONAS.items():
        assert p.persona_id == pid
        assert p.name
        assert p.technical_level in ("low", "medium", "high")
        assert p.goal
        assert p.motivation
        assert isinstance(p.risk_focus, list)
        assert isinstance(p.expected_confusion, list)
        assert isinstance(p.tasks_to_run, list)
        assert len(p.tasks_to_run) > 0
        assert p.success_definition
        assert isinstance(p.failure_signals, list)


def test_get_persona_returns_correct_persona():
    """get_persona should return the right persona by ID."""
    p = get_persona("P01")
    assert p is not None
    assert p.name == "Novice Student Founder"


def test_get_persona_returns_none_for_missing():
    """get_persona should return None for unknown ID."""
    assert get_persona("P99") is None


def test_list_personas_returns_all():
    """list_personas should return all 12 personas."""
    personas = list_personas()
    assert len(personas) == 12


def test_persona_tasks_exist():
    """All task IDs referenced in personas should be valid."""
    from app.beta.synthetic_tester.tasks import get_task

    for p in PERSONAS.values():
        for task_id in p.tasks_to_run:
            assert get_task(task_id) is not None, f"Persona {p.persona_id} references unknown task {task_id}"


def test_persona_id_uniqueness():
    """All persona IDs must be unique."""
    ids = [p.persona_id for p in PERSONAS.values()]
    assert len(ids) == len(set(ids))


def test_persona_technical_levels_covered():
    """Should have personas at all technical levels."""
    levels = {p.technical_level for p in PERSONAS.values()}
    assert "low" in levels
    assert "medium" in levels
    assert "high" in levels


def test_privacy_user_has_privacy_focus():
    """Privacy persona must have privacy data concerns."""
    p = get_persona("P09")
    assert p is not None
    assert any("data" in f.lower() or "secret" in f.lower() for f in p.risk_focus)
