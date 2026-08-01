"""
Kill-Switch Recovery Test (B7).

Verifies the kill-switch fails CLOSED (blocks all trading) on every form of
state-file corruption. This is a paper-trade safety test only — no live broker
is contacted, no order is sent.

Scenarios:
  1. State file MISSING  -> first run, must be INACTIVE (no spurious trigger).
  2. State file CORRUPTED (bad JSON) -> must fail-CLOSED (ACTIVE).
  3. State file with INVALID state value -> must fail-CLOSED (ACTIVE).
  4. State file written by older version (missing required keys) -> must
     still load without KeyError; INACTIVE preserved, ACTIVE preserved.
  5. Round-trip then mid-flight corruption -> must fail-CLOSED (ACTIVE).
  6. activate() on read-only state file -> must raise, not swallow.

Usage:
    python scripts/test_kill_switch_recovery.py [--keep-tmp]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from risk.kill_switch import KillSwitch, KillSwitchState  # noqa: E402


PASS = "PASS"
FAIL = "FAIL"


def _banner(text):
    print()
    print("=" * 72)
    print(f"  {text}")
    print("=" * 72)


def _assert(cond, label, detail=""):
    status = PASS if cond else FAIL
    flag = "OK  " if cond else "XX  "
    print(f"  [{flag}] {label}{(' - ' + detail) if detail else ''}")
    return status, label


def scenario_1_missing_file(tmp):
    """Brand-new install with no state file must read INACTIVE."""
    _banner("Scenario 1: state file missing (first run)")
    state_path = tmp / "kill_switch_state.json"
    assert not state_path.exists()

    ks = KillSwitch(state_file=str(state_path))
    status_enum = ks._get_state_enum()

    results = []
    results.append(_assert(
        status_enum == KillSwitchState.INACTIVE,
        "missing file -> INACTIVE",
        f"got {status_enum.value}",
    ))
    results.append(_assert(
        ks.is_active() is False,
        "is_active() == False",
    ))
    results.append(_assert(
        ks.is_triggered is False,
        "is_triggered == False (no spurious trading halt)",
    ))
    return results


def scenario_2_corrupt_json(tmp):
    """A JSON-garbled state file MUST be quarantined AND fail-CLOSED."""
    _banner("Scenario 2: corrupt JSON (fail-closed)")
    state_path = tmp / "kill_switch_state.json"
    state_path.write_text(
        '{"state": "ACTIVE", "reason": "test", oops missing quote',
        encoding="utf-8",
    )

    ks = KillSwitch(state_file=str(state_path))
    status_enum = ks._get_state_enum()
    corrupt_siblings = list(tmp.glob("kill_switch_state.corrupt.*.json"))

    results = []
    results.append(_assert(
        status_enum == KillSwitchState.ACTIVE,
        "corrupt JSON -> ACTIVE (fail-closed)",
        f"got {status_enum.value}",
    ))
    results.append(_assert(
        ks.is_active() is True,
        "is_active() == True (trading halted)",
    ))
    results.append(_assert(
        ks.is_triggered is True,
        "is_triggered == True",
    ))
    results.append(_assert(
        len(corrupt_siblings) == 1,
        "corrupt file quarantined to .corrupt.<ts>.json",
        f"found {len(corrupt_siblings)} quarantine file(s)",
    ))
    results.append(_assert(
        not state_path.exists(),
        "original state file removed (moved to .corrupt.*)",
    ))
    return results


def scenario_3_invalid_state_value(tmp):
    """An unknown state value MUST be treated as ACTIVE (fail-closed)."""
    _banner("Scenario 3: invalid state value (e.g. 'BANANAS')")
    state_path = tmp / "kill_switch_state.json"
    state_path.write_text(
        json.dumps({"state": "BANANAS", "reason": "test"}),
        encoding="utf-8",
    )

    ks = KillSwitch(state_file=str(state_path))
    status_enum = ks._get_state_enum()

    results = []
    results.append(_assert(
        status_enum == KillSwitchState.ACTIVE,
        "unknown state value -> ACTIVE (fail-closed)",
        f"got {status_enum.value}",
    ))
    results.append(_assert(
        ks.is_active() is True,
        "is_active() == True",
    ))
    results.append(_assert(
        ks.is_triggered is True,
        "is_triggered == True",
    ))
    return results


def scenario_4_unwritable_state_file(tmp):
    """activate() on a read-only state file MUST raise, never silently swallow."""
    _banner("Scenario 4: state file not writable (read-only)")
    state_path = tmp / "kill_switch_state.json"
    state_path.write_text(
        json.dumps({"state": "INACTIVE", "reason": "", "killed_classes": []}),
        encoding="utf-8",
    )

    if os.name == "nt":
        os.chmod(state_path, 0o444)
    else:
        os.chmod(state_path, 0o444)

    ks = KillSwitch(state_file=str(state_path))
    raised = False
    err_msg = ""
    try:
        ks.activate("test", source="recovery_test")
    except OSError as exc:
        raised = True
        err_msg = str(exc)
    except Exception as exc:  # noqa: BLE001
        raised = True
        err_msg = f"{type(exc).__name__}: {exc}"
    finally:
        if os.name == "nt":
            os.chmod(state_path, 0o666)
        else:
            os.chmod(state_path, 0o644)

    results = []
    results.append(_assert(
        raised,
        "activate() raised on unwritable state (no silent swallow)",
        err_msg or "no exception raised - BUG",
    ))
    return results


def scenario_5_legacy_state_missing_keys(tmp):
    """Old-schema state files with missing keys must not raise KeyError."""
    _banner("Scenario 5: legacy state missing required keys")
    state_path = tmp / "kill_switch_state.json"
    state_path.write_text(json.dumps({"state": "INACTIVE"}), encoding="utf-8")

    ks = KillSwitch(state_file=str(state_path))
    status_enum = ks._get_state_enum()

    results = []
    # Old INACTIVE state with missing keys is not corruption; defaults filled
    # in. Result stays INACTIVE (expected non-fail-closed path).
    results.append(_assert(
        status_enum == KillSwitchState.INACTIVE,
        "legacy INACTIVE w/ missing keys -> INACTIVE (no spurious halt)",
        f"got {status_enum.value}",
    ))
    results.append(_assert(
        ks.is_active() is False,
        "is_active() == False",
    ))

    # Old ACTIVE file with missing keys must not raise and must remain ACTIVE.
    state_path2 = tmp / "kill_switch_state_legacy_active.json"
    state_path2.write_text(json.dumps({"state": "ACTIVE"}), encoding="utf-8")
    ks2 = KillSwitch(state_file=str(state_path2))
    results.append(_assert(
        ks2.is_active() is True,
        "legacy ACTIVE w/ missing keys -> still ACTIVE (no key error)",
        f"is_active={ks2.is_active()}",
    ))
    return results


def scenario_6_round_trip_then_corrupt(tmp):
    """Activate -> write -> corrupt mid-flight -> reload -> must be fail-closed."""
    _banner("Scenario 6: round-trip + mid-flight corruption")
    state_path = tmp / "kill_switch_state.json"
    ks = KillSwitch(state_file=str(state_path))
    ks.deactivate("initial", authorized_by="recovery_test")
    assert ks.is_active() is False

    ks.activate("test trigger", source="recovery_test")
    assert state_path.exists(), "state file should exist after activate"
    assert ks.is_active() is True

    # Truncate the file mid-flight.
    state_path.write_text("}{ garbage", encoding="utf-8")

    ks2 = KillSwitch(state_file=str(state_path))
    is_active = ks2.is_active()
    results = []
    results.append(_assert(
        is_active is True,
        "fresh reload after mid-flight corruption -> ACTIVE (fail-closed)",
        f"is_active={is_active}",
    ))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="Keep the temp directory after tests for inspection",
    )
    args = parser.parse_args()

    print("Kill-Switch Recovery Test (B7) - fail-closed verification")
    print("  No live broker. No orders. Pure state-file recovery logic.")

    tmp_root = Path(tempfile.mkdtemp(prefix="kill_switch_recovery_"))
    print(f"  tmp dir: {tmp_root}")

    all_results = []
    scenarios = [
        scenario_1_missing_file,
        scenario_2_corrupt_json,
        scenario_3_invalid_state_value,
        scenario_4_unwritable_state_file,
        scenario_5_legacy_state_missing_keys,
        scenario_6_round_trip_then_corrupt,
    ]

    try:
        for scenario in scenarios:
            tmp = tmp_root / scenario.__name__
            tmp.mkdir(parents=True, exist_ok=True)
            try:
                all_results.extend(scenario(tmp))
            except Exception:  # noqa: BLE001
                tb = traceback.format_exc()
                all_results.append((FAIL, f"{scenario.__name__} - unhandled exception"))
                print(f"  [XX  ] {scenario.__name__} raised:\n{tb}")
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)
        else:
            print(f"  --keep-tmp set; leaving {tmp_root} for inspection")

    _banner("Summary")
    passed = sum(1 for s, _ in all_results if s == PASS)
    failed = sum(1 for s, _ in all_results if s == FAIL)
    for status, label in all_results:
        flag = "OK  " if status == PASS else "XX  "
        print(f"  [{flag}] {label}")
    print()
    print(f"  {passed} passed, {failed} failed, {len(all_results)} total")
    if failed:
        print("  RESULT: FAIL - kill-switch recovery has gaps.")
        return 1
    print("  RESULT: PASS - kill-switch fails closed on every corruption class.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
