"""Tests for symbol-level kill switch (Phase 1 demote wiring)."""

from __future__ import annotations

import json

from graxia.packages.quant_os.risk.kill_switch import KillSwitch


def _make(tmp_path) -> KillSwitch:
    return KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))


def test_kill_symbol_appends_and_reports(tmp_path):
    ks = _make(tmp_path)
    out = ks.kill_symbol("XAUUSD", "cost drift", source="demote:cost_drift")
    assert "XAUUSD" in out
    assert ks.is_symbol_killed("XAUUSD")
    assert not ks.is_symbol_killed("USOIL")
    assert "XAUUSD" in ks.get_status()["killed_symbols"]


def test_kill_symbol_is_idempotent(tmp_path):
    ks = _make(tmp_path)
    ks.kill_symbol("XAUUSD", "r")
    ks.kill_symbol("XAUUSD", "r")
    assert ks.get_status()["killed_symbols"] == ["XAUUSD"]


def test_active_state_kills_all_symbols(tmp_path):
    ks = _make(tmp_path)
    ks.activate("test", source="unit-test")
    assert ks.is_symbol_killed("ANYTHING")


def test_deactivate_clears_symbol_kills(tmp_path):
    ks = _make(tmp_path)
    ks.kill_symbol("XAUUSD", "r")
    ks.deactivate("clear", authorized_by="test")
    assert not ks.is_symbol_killed("XAUUSD")
    assert ks.get_status()["killed_symbols"] == []


def test_symbol_kills_persist_across_reload(tmp_path):
    state_file = tmp_path / "kill_switch_state.json"
    ks1 = KillSwitch(state_file=str(state_file))
    ks1.kill_symbol("XAUUSD", "r")
    ks2 = KillSwitch(state_file=str(state_file))
    assert ks2.is_symbol_killed("XAUUSD")


def test_existing_state_without_key_does_not_break(tmp_path):
    state_file = tmp_path / "kill_switch_state.json"
    state_file.write_text(
        json.dumps(
            {
                "state": "INACTIVE",
                "killed_classes": [],
                "reason": "",
                "activated_at_utc": None,
                "authorized_by": "",
                "history": [],
            }
        )
    )
    ks = KillSwitch(state_file=str(state_file))
    assert ks.is_symbol_killed("XAUUSD") is False
    assert ks.get_status()["killed_symbols"] == []


def test_corrupt_state_fail_closed_includes_symbol_key(tmp_path):
    state_file = tmp_path / "kill_switch_state.json"
    state_file.write_text("{corrupt")
    ks = KillSwitch(state_file=str(state_file))
    assert ks.is_active()
    assert ks.get_status()["killed_symbols"] == []
