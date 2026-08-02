"""Regression tests for circuit-breaker follow-up (shared state + restart recovery).

Covers:
- ``opened_at`` is persisted in the state file (v2 schema) so cooldown
  recovery works across process restarts.
- Legacy v1 files (no ``oa`` field) load fail-closed: an open breaker
  stays open until manual reset.
- ``DEFAULT_STATE_FILE`` is the canonical shared path used by all
  production entry points (orchestrator, risk_bridge, webhook,
  signal_service).
- ``get_status()`` exposes ``opened_at`` per class (additive).
"""

import json
import time
from pathlib import Path

from graxia.packages.quant_os.risk.circuit_breaker import (
    DEFAULT_STATE_FILE,
    CircuitBreaker,
    CircuitBreakerConfig,
)


def _write_state(state_file: Path, payload: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(payload), encoding="utf-8")


def test_save_persists_opened_at(tmp_path):
    """trip() must persist opened_at so a reloaded breaker auto-recovers."""
    state_file = tmp_path / "circuit_breaker_state.json"
    cb = CircuitBreaker(state_file=str(state_file))
    cb.trip("metals", reason="test trip")
    assert cb.is_open("metals") is True

    reloaded = CircuitBreaker(state_file=str(state_file))
    assert reloaded.is_open("metals") is True
    status = reloaded.get_status()
    assert status["metals"]["opened_at"] > 0.0


def test_cooldown_recovery_across_restart(tmp_path):
    """A breaker tripped in a previous process recovers after cooldown."""
    state_file = tmp_path / "circuit_breaker_state.json"
    cb = CircuitBreaker(
        state_file=str(state_file),
        config=CircuitBreakerConfig(threshold=1, cooldown_minutes=30),
    )
    cb.record_trade("crypto", pnl=-10.0)
    assert cb.is_open("crypto") is True

    # Simulate restart long after the trip: backdate opened_at in the file.
    data = json.loads(state_file.read_text(encoding="utf-8"))
    data["crypto"]["oa"] = time.time() - 3600
    _write_state(state_file, data)

    reloaded = CircuitBreaker(
        state_file=str(state_file),
        config=CircuitBreakerConfig(threshold=1, cooldown_minutes=30),
    )
    assert reloaded.is_open("crypto") is False


def test_legacy_file_without_opened_at_stays_open(tmp_path):
    """v1 state files (no 'oa') fail closed: open stays open, no crash."""
    state_file = tmp_path / "circuit_breaker_state.json"
    _write_state(state_file, {"metals": {"cl": 3, "o": True, "r": "legacy trip", "tc": 1}})

    cb = CircuitBreaker(state_file=str(state_file))
    assert cb.is_open("metals") is True
    assert cb.get_status()["metals"]["opened_at"] == 0.0


def test_legacy_untripped_file_loads_clean(tmp_path):
    """v1 state file without the 'oa' field and not open loads without trip."""
    state_file = tmp_path / "circuit_breaker_state.json"
    _write_state(state_file, {"metals": {"cl": 2, "o": False, "r": "", "tc": 0}})

    cb = CircuitBreaker(state_file=str(state_file))
    assert cb.is_open("metals") is False
    assert cb.get_status()["metals"]["consecutive_losses"] == 2


def test_default_state_file_is_shared_canonical_path():
    """DEFAULT_STATE_FILE is the CWD-relative path mirroring KillSwitch."""
    assert DEFAULT_STATE_FILE == "data/circuit_breaker_state.json"


def test_status_includes_opened_at(tmp_path):
    """get_status() exposes opened_at per class (additive observability)."""
    state_file = tmp_path / "circuit_breaker_state.json"
    cb = CircuitBreaker(state_file=str(state_file))
    cb.trip("indices", reason="manual")
    status = cb.get_status()
    assert status["indices"]["opened_at"] > 0.0
    assert status["metals"]["opened_at"] == 0.0
