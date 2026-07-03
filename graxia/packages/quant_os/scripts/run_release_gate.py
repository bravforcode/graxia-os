"""Phase 3.1A.1 — Release gate: fail-closed, two clean subprocess runs, compare results.

Usage: python scripts/run_release_gate.py
"""

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # graxia os root
ARTIFACT_DIR = REPO_ROOT / "graxia/packages/quant_os/artifacts/release_gate"
QUARANTINE_PATH = REPO_ROOT / "graxia/packages/quant_os/quarantine_manifest.json"

RELEASE_GATE_CONFIG = {
    "required_collected_tests": 552,
    "required_passed_tests": 552,  # all must pass
    "allowed_failed_tests": 0,
    "allowed_errors": 0,
    "allowed_xfailed": 0,
    "allowed_xpassed": 0,
    "allowed_unapproved_skips": 2,  # test_vwap (deprecated) + test_engine_ledger_tamper (multi-trade)
    "allowed_timeouts": 0,
    "required_reproducibility_runs": 2,
    "required_equal_ledger_seal_hashes": True,
}

SUITE_CMD = [
    sys.executable,
    "-m",
    "pytest",
    "graxia/packages/quant_os/tests/",
    "--tb=short",
    "-q",
    "--ignore=graxia/packages/quant_os/tests/test_vwap.py",
]
E2E_SCRIPT = str(Path(__file__).parent / "e2e_release_gate.py")
E2E_CMD = [sys.executable, E2E_SCRIPT]


def get_git_sha():
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.stdout.strip()


def get_python_version():
    return sys.version


def get_lock_hash():
    """Hash pip freeze output."""
    r = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
    return hashlib.sha256(r.stdout.encode()).hexdigest()


def get_git_status():
    """Return untracked/modified files from git status --porcelain."""
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.stdout.strip()


def get_e2e_seal(e2e_output):
    """Extract ledger seal from E2E output."""
    for line in e2e_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if "seal" in data:
                return data["seal"]
        except json.JSONDecodeError:
            continue
    return None


def parse_pytest_output(output):
    """Parse pytest output for pass/fail/error/skip/xfail/xpass counts."""
    stats = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0, "xpassed": 0}

    # Match summary lines in both formats:
    #   "-q": "3 failed, 559 passed, 2 warnings in 50.75s"
    #   default: "=== 3 failed, 559 passed ... in 50.75s ==="
    # Grab the last non-empty line as the summary
    lines = [l for l in output.strip().split("\n") if l.strip()]
    if lines:
        summary = lines[-1]
        for key in stats:
            m = re.search(rf"(\d+)\s+{key}", summary)
            if m:
                stats[key] = int(m.group(1))

    return stats


def load_quarantine_manifest():
    """Load quarantine manifest if it exists, return (data, path_exists)."""
    if QUARANTINE_PATH.exists():
        with open(QUARANTINE_PATH) as f:
            return json.load(f), True
    return None, False


def count_ignored_quarantined(quarantine_data):
    """Count quarantined tests that are --ignored by pytest (not collected, so not in skip count)."""
    if not quarantine_data:
        return 0
    count = 0
    for entry in quarantine_data.get("quarantined_tests", []):
        test_file = entry.get("test_file", "")
        if test_file and any(test_file in cmd_arg for cmd_arg in SUITE_CMD if "--ignore" in cmd_arg):
            count += 1
    return count


def check_quarantine_consistency(pytest_stats, quarantine_data):
    """Verify skipped tests match quarantine manifest.

    Quarantined tests can appear as either:
    - pytest skipped (if marked with @pytest.mark.skip)
    - not collected at all (if --ignored in SUITE_CMD)
    """
    errors = []
    skipped = pytest_stats["skipped"]
    ignored_quarantined = count_ignored_quarantined(quarantine_data)
    effective_quarantined = skipped + ignored_quarantined

    if not quarantine_data:
        if skipped > 0:
            errors.append(f"Skipped tests ({skipped}) but no quarantine_manifest.json found")
        return errors

    quarantine_count = quarantine_data.get("total_quarantined", 0)

    if quarantine_count == 0 and effective_quarantined > 0:
        errors.append(
            f"Quarantined tests ({effective_quarantined} = {skipped} skipped + {ignored_quarantined} ignored) "
            f"but quarantine manifest has 0 entries"
        )
    elif effective_quarantined > quarantine_count:
        errors.append(f"More quarantined tests ({effective_quarantined}) than manifest entries ({quarantine_count})")
    elif effective_quarantined < quarantine_count:
        errors.append(f"Fewer quarantined tests ({effective_quarantined}) than manifest entries ({quarantine_count})")

    return errors


def run_suite(label):
    """Run the test suite in a fresh subprocess."""
    run_dir = ARTIFACT_DIR / label
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write env info
    (run_dir / "git_commit.txt").write_text(get_git_sha())
    (run_dir / "python_version.txt").write_text(get_python_version())
    (run_dir / "lockfile_sha256.txt").write_text(get_lock_hash())
    (run_dir / "pytest_command.txt").write_text(" ".join(SUITE_CMD))

    # Run suite
    t0 = time.time()
    r = subprocess.run(SUITE_CMD, capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT))
    dt = time.time() - t0

    (run_dir / "pytest_output.txt").write_text(r.stdout + "\n" + r.stderr)

    # Parse results
    stats = parse_pytest_output(r.stdout)
    result = {
        "returncode": r.returncode,
        "duration_s": round(dt, 2),
        "stdout_lines": len(r.stdout.split("\n")),
        "stats": stats,
    }
    (run_dir / "test_result.json").write_text(json.dumps(result, indent=2))

    # Run E2E
    r2 = subprocess.run(E2E_CMD, capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT))
    e2e_output = r2.stdout + "\n" + r2.stderr
    (run_dir / "e2e_output.txt").write_text(e2e_output)

    e2e_seal = get_e2e_seal(r2.stdout)
    result["e2e_seal"] = e2e_seal

    return result, r.stdout


def check_fail_closed(stats):
    """Fail-closed checks on parsed pytest output."""
    errors = []
    cfg = RELEASE_GATE_CONFIG

    total = stats["passed"] + stats["failed"] + stats["errors"] + stats["skipped"]
    if total < cfg["required_collected_tests"]:
        errors.append(f"Collection count {total} < required {cfg['required_collected_tests']}")

    if stats["failed"] > cfg["allowed_failed_tests"]:
        errors.append(f"Failed tests {stats['failed']} > allowed {cfg['allowed_failed_tests']}")
    if stats["errors"] > cfg["allowed_errors"]:
        errors.append(f"Test errors {stats['errors']} > allowed {cfg['allowed_errors']}")
    if stats["xfailed"] > cfg["allowed_xfailed"]:
        errors.append(f"Xfailed tests {stats['xfailed']} > allowed {cfg['allowed_xfailed']}")
    if stats["xpassed"] > cfg["allowed_xpassed"]:
        errors.append(f"Xpassed tests {stats['xpassed']} > allowed {cfg['allowed_xpassed']}")
    if stats["skipped"] > cfg["allowed_unapproved_skips"]:
        errors.append(f"Skipped tests {stats['skipped']} > allowed unapproved {cfg['allowed_unapproved_skips']}")

    if stats["passed"] < cfg["required_passed_tests"]:
        errors.append(f"Passed count {stats['passed']} < required {cfg['required_passed_tests']}")

    return errors


def compare_runs(a_result, b_result, a_output, b_output):
    """Compare two runs — pass if both produce identical results."""
    errors = []

    if a_result["returncode"] != b_result["returncode"]:
        errors.append(f"Return code mismatch: A={a_result['returncode']} B={b_result['returncode']}")

    a_s, b_s = a_result["stats"], b_result["stats"]
    if a_s["passed"] != b_s["passed"]:
        errors.append(f"Pass count mismatch: A={a_s['passed']} B={b_s['passed']}")
    if a_s["failed"] != b_s["failed"]:
        errors.append(f"Fail count mismatch: A={a_s['failed']} B={b_s['failed']}")
    if a_s["errors"] != b_s["errors"]:
        errors.append(f"Error count mismatch: A={a_s['errors']} B={b_s['errors']}")
    if a_s["skipped"] != b_s["skipped"]:
        errors.append(f"Skip count mismatch: A={a_s['skipped']} B={b_s['skipped']}")

    return errors


def check_git_clean():
    """Fail if uncommitted changes exist (except quarantine manifest)."""
    status = get_git_status()
    if not status:
        return []

    dirty_files = []
    for line in status.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Extract file path after status codes
        filepath = line[3:].strip()
        if filepath == "graxia/packages/quant_os/quarantine_manifest.json":
            continue
        dirty_files.append(filepath)

    if dirty_files:
        return [f"Uncommitted changes: {', '.join(dirty_files)}"]
    return []


def check_ledger_seal(a_result, b_result):
    """Compare E2E ledger seals from run A vs run B."""
    if not RELEASE_GATE_CONFIG["required_equal_ledger_seal_hashes"]:
        return []

    a_seal = a_result.get("e2e_seal")
    b_seal = b_result.get("e2e_seal")

    if not a_seal:
        return ["Run A: no ledger seal found in E2E output"]
    if not b_seal:
        return ["Run B: no ledger seal found in E2E output"]
    if a_seal != b_seal:
        return [f"Ledger seal mismatch: A={a_seal} B={b_seal}"]

    return []


def main():
    print("Phase 3.1A.1 Release Gate — Fail-Closed, Two Clean-Process Runs")
    print("=" * 60)

    all_failures = []
    checks = {}

    # --- Git status check (before running anything) ---
    print("\n--- Git Status Check ---")
    git_errors = check_git_clean()
    checks["git_clean"] = len(git_errors) == 0
    all_failures.extend(git_errors)
    print(f"git_clean: {checks['git_clean']}")

    # --- Quarantine consistency (before running) ---
    print("\n--- Quarantine Check ---")
    quarantine_data, quarantine_exists = load_quarantine_manifest()
    print(f"quarantine_manifest exists: {quarantine_exists}")

    # --- Run A ---
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n--- Run A ---")
    a_result, a_output = run_suite("run_a")
    print(f"Duration: {a_result['duration_s']}s, RC: {a_result['returncode']}")
    print(f"Stats: {a_result['stats']}")

    # --- Run B ---
    print("\n--- Run B ---")
    b_result, b_output = run_suite("run_b")
    print(f"Duration: {b_result['duration_s']}s, RC: {b_result['returncode']}")
    print(f"Stats: {b_result['stats']}")

    # --- Fail-closed checks (Run A) ---
    print("\n--- Fail-Closed Checks (Run A) ---")
    fc_errors_a = check_fail_closed(a_result["stats"])
    checks["collection_clean"] = (
        a_result["stats"]["passed"]
        + a_result["stats"]["failed"]
        + a_result["stats"]["errors"]
        + a_result["stats"]["skipped"]
    ) >= RELEASE_GATE_CONFIG["required_collected_tests"]
    checks["all_passed"] = a_result["stats"]["failed"] == 0 and a_result["stats"]["errors"] == 0
    checks["no_failures"] = a_result["stats"]["failed"] == 0
    checks["no_errors"] = a_result["stats"]["errors"] == 0
    checks["no_flaky"] = a_result["stats"]["xfailed"] == 0 and a_result["stats"]["xpassed"] == 0
    all_failures.extend(fc_errors_a)
    for k, v in checks.items():
        print(f"  {k}: {v}")

    # --- Quarantine consistency ---
    print("\n--- Quarantine Consistency ---")
    ignored_q = count_ignored_quarantined(quarantine_data)
    print(f"  skipped: {a_result['stats']['skipped']}, ignored+quarantined: {ignored_q}")
    q_errors = check_quarantine_consistency(a_result["stats"], quarantine_data)
    checks["quarantine_consistent"] = len(q_errors) == 0
    all_failures.extend(q_errors)
    print(f"  quarantine_consistent: {checks['quarantine_consistent']}")

    # --- Reproducibility ---
    print("\n--- Reproducibility ---")
    repro_errors = compare_runs(a_result, b_result, a_output, b_output)
    checks["reproducible"] = len(repro_errors) == 0
    all_failures.extend(repro_errors)
    print(f"  reproducible: {checks['reproducible']}")

    # --- Ledger seal ---
    print("\n--- Ledger Seal ---")
    seal_errors = check_ledger_seal(a_result, b_result)
    checks["ledger_seal_match"] = len(seal_errors) == 0
    all_failures.extend(seal_errors)
    print(f"  ledger_seal_match: {checks['ledger_seal_match']}")

    # --- Final verdict ---
    verdict = "PASS" if not all_failures else "FAIL"
    print(f"\n{'=' * 60}")
    print(f"VERDICT: {verdict}")

    if all_failures:
        print("\nFAILURE DETAILS:")
        for f in all_failures:
            print(f"  - {f}")

    # --- Write summary ---
    summary = {
        "run_a": a_result,
        "run_b": b_result,
        "checks": checks,
        "verdict": verdict,
        "failures": all_failures,
    }
    (ARTIFACT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {ARTIFACT_DIR / 'summary.json'}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
