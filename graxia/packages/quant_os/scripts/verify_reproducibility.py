"""Phase BE-P1 — Verify release reproducibility via dual runs."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def run_release(root: str) -> dict:
    """Run release truth capture and return results."""
    result = subprocess.run(
        [sys.executable, "graxia/packages/quant_os/scripts/run_release_truth.py", root],
        capture_output=True, text=True, timeout=600, cwd=root
    )
    if result.returncode != 0:
        return {"error": result.stderr[:500]}
    
    # Parse the JSON output
    lines = result.stdout.strip().splitlines()
    # Find the JSON block (starts with {)
    json_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break
    
    if json_start is None:
        return {"error": "No JSON output found"}
    
    json_str = "\n".join(lines[json_start:])
    return json.loads(json_str)


def compare_runs(run1: dict, run2: dict) -> tuple[bool, list[str]]:
    """Compare two release runs for reproducibility."""
    issues = []
    
    # Compare git commit
    if run1.get("artifacts", {}).get("git_commit") != run2.get("artifacts", {}).get("git_commit"):
        issues.append("git_commit mismatch")
    
    # Compare test output hash
    hash1 = run1.get("artifacts", {}).get("full_bundle_hash")
    hash2 = run2.get("artifacts", {}).get("full_bundle_hash")
    if hash1 != hash2:
        issues.append(f"bundle_hash mismatch: {hash1} vs {hash2}")
    
    # Compare dependency lock
    lock1 = run1.get("artifacts", {}).get("dependency_lock_hash")
    lock2 = run2.get("artifacts", {}).get("dependency_lock_hash")
    if lock1 != lock2:
        issues.append(f"dependency_lock_hash mismatch")
    
    return len(issues) == 0, issues


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print("Run 1/2...")
    run1 = run_release(root)
    if "error" in run1:
        print(f"Run 1 failed: {run1['error']}")
        return 1
    
    print("Run 2/2...")
    run2 = run_release(root)
    if "error" in run2:
        print(f"Run 2 failed: {run2['error']}")
        return 1
    
    match, issues = compare_runs(run1, run2)
    
    if match:
        print("PASS: Two runs match")
        print(f"  Commit: {run1['artifacts']['git_commit']}")
        print(f"  Bundle hash: {run1['artifacts']['full_bundle_hash']}")
        return 0
    else:
        print("FAIL: Runs do not match")
        for issue in issues:
            print(f"  - {issue}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
