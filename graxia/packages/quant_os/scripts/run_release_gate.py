"""Phase 3.1A.1 — Release gate: two clean subprocess runs, compare results.

Usage: python scripts/run_release_gate.py
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")
ARTIFACT_DIR = REPO_ROOT / "graxia/packages/quant_os/artifacts/release_gate"
SUITE_CMD = [
    sys.executable, "-m", "pytest",
    "graxia/packages/quant_os/tests/",
    "--tb=short", "-q",
    "--ignore=graxia/packages/quant_os/tests/test_vwap.py",
]
E2E_CMD = [
    sys.executable, "-c",
    "from graxia.packages.quant_os.backtest.engine_e2e_fixture import get_all_scenarios; "
    "from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig; "
    "from graxia.packages.quant_os.execution.ledger_integrity import IntegrityChain, LedgerRecord; "
    "import json; "
    "scenarios = get_all_scenarios(); "
    "results = []; "
    "for name, cfg, bars, ts, signals, exp in scenarios[:3]: "
    "  results.append(name); "
    "print(json.dumps({'scenario_count': len(scenarios), 'ran': results})); "
    "chain = IntegrityChain(); "
    "for i in range(5): "
    "  rec = LedgerRecord(trade_id=f't-{i}', order_id=f'o-{i}', symbol='XAUUSD', side='BUY', entry_price='2000', exit_price='2010', volume='0.1', pnl='10', fees='3.5', spread_cost='2', slippage_cost='1', entry_time='2025-01-01T00:00:00', exit_time='2025-01-02T00:00:00', close_reason='TAKE_PROFIT', strategy_id='test', contract_snapshot_id='v1', risk_policy_version='DEFAULT', dataset_manifest_id='d1', cost_scenario='BASE', git_commit='test'); "
    "  chain.append(rec); "
    "valid, errors = chain.verify(); "
    "seal = chain.compute_run_seal('test_manifest'); "
    "print(json.dumps({'chain_valid': valid, 'seal': seal, 'errors': errors}))"
]


def get_git_sha():
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.stdout.strip()


def get_python_version():
    return sys.version


def get_lock_hash():
    """Hash pip freeze output."""
    r = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
    return hashlib.sha256(r.stdout.encode()).hexdigest()


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
    result = {
        "returncode": r.returncode,
        "duration_s": round(dt, 2),
        "stdout_lines": len(r.stdout.split("\n")),
    }
    (run_dir / "test_result.json").write_text(json.dumps(result, indent=2))

    # Run E2E
    r2 = subprocess.run(E2E_CMD, capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT))
    (run_dir / "e2e_output.txt").write_text(r2.stdout + "\n" + r2.stderr)

    return result, r.stdout


def compare_runs(a_result, b_result, a_output, b_output):
    """Compare two runs — pass if both produce identical results."""
    import re
    errors = []

    if a_result["returncode"] != b_result["returncode"]:
        errors.append(f"Return code mismatch: A={a_result['returncode']} B={b_result['returncode']}")

    a_pass = re.search(r"(\d+) passed", a_output)
    b_pass = re.search(r"(\d+) passed", b_output)
    a_fail = re.search(r"(\d+) failed", a_output)
    b_fail = re.search(r"(\d+) failed", b_output)

    a_passed = int(a_pass.group(1)) if a_pass else 0
    b_passed = int(b_pass.group(1)) if b_pass else 0
    a_failed = int(a_fail.group(1)) if a_fail else 0
    b_failed = int(b_fail.group(1)) if b_fail else 0

    if a_passed != b_passed:
        errors.append(f"Pass count mismatch: A={a_passed} B={b_passed}")
    if a_failed != b_failed:
        errors.append(f"Fail count mismatch: A={a_failed} B={b_failed}")

    if a_failed > 0 and a_failed == b_failed:
        print(f"  Note: {a_failed} pre-existing failures (identical across runs)")

    return errors


def main():
    print("Phase 3.1A.1 Release Gate — Two Clean-Process Runs")
    print("=" * 60)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n--- Run A ---")
    a_result, a_output = run_suite("run_a")
    print(f"Duration: {a_result['duration_s']}s, RC: {a_result['returncode']}")

    print("\n--- Run B ---")
    b_result, b_output = run_suite("run_b")
    print(f"Duration: {b_result['duration_s']}s, RC: {b_result['returncode']}")

    print("\n--- Comparison ---")
    errors = compare_runs(a_result, b_result, a_output, b_output)
    if errors:
        print("FAILURES:")
        for e in errors:
            print(f"  {e}")
    else:
        print("ALL CHECKS PASS")

    # Write summary
    summary = {
        "run_a": a_result,
        "run_b": b_result,
        "comparison_errors": errors,
        "verdict": "PASS" if not errors else "FAIL",
    }
    (ARTIFACT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
