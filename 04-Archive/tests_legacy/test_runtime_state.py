from app.core.runtime_state import get_runtime_state, set_runtime_state


def test_runtime_state_round_trip():
    set_runtime_state(False, "blocked", ["database unavailable"])
    state = get_runtime_state()

    assert state["is_ready"] is False
    assert state["mode"] == "blocked"
    assert state["issues"] == ["database unavailable"]
    assert state["updated_at"] is not None
