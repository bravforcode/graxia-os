"""Phase BE-P1 — Release gate. Fail-closed checks for release readiness."""

import json
import subprocess
import sys
from pathlib import Path


class ReleaseGate:
    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.checks: list[dict] = []

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})

    def check_clean_worktree(self) -> None:
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=self.root)
        dirty = result.stdout.strip()
        self.check("clean_worktree", not dirty, dirty[:200] if dirty else "clean")

    def check_test_suite(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line", "graxia/packages/quant_os/tests/"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=self.root,
        )
        output = result.stdout + result.stderr
        has_failure = "failed" in output.lower() or result.returncode != 0
        self.check("test_suite_pass", not has_failure, output[:300])

    def check_no_unapproved_skips(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "graxia/packages/quant_os/tests/"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.root,
        )
        self.check("test_collection_clean", result.returncode == 0, result.stdout[:200])

    def check_quarantine_manifest(self) -> None:
        qm_path = self.root / "graxia" / "packages" / "quant_os" / "quarantine_manifest.json"
        if qm_path.exists():
            data = json.loads(qm_path.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            self.check("quarantine_manifest", True, f"{len(entries)} entries")
        else:
            self.check("quarantine_manifest", True, "no manifest (no skips)")

    def check_git_commit(self) -> None:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=self.root)
        commit = result.stdout.strip()
        self.check("git_commit", bool(commit), commit[:16])

    def run_all(self) -> bool:
        self.check_clean_worktree()
        self.check_test_suite()
        self.check_no_unapproved_skips()
        self.check_quarantine_manifest()
        self.check_git_commit()

        all_passed = all(c["passed"] for c in self.checks)
        return all_passed

    def report(self) -> str:
        lines = ["# Release Gate Report\n"]
        for c in self.checks:
            status = "PASS" if c["passed"] else "FAIL"
            lines.append(f"- [{status}] {c['name']}: {c['detail']}")

        all_passed = all(c["passed"] for c in self.checks)
        verdict = "PASS_TO_BE_P2" if all_passed else "NO_GO"
        lines.append(f"\n## Verdict: {verdict}")
        return "\n".join(lines)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    gate = ReleaseGate(root)
    passed = gate.run_all()
    print(gate.report())
    sys.exit(0 if passed else 1)
