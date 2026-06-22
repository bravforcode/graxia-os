"""Phase BE-P1 — Release truth runner. Captures reproducible release artifacts."""
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class ReleaseTruthRunner:
    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.output_dir = self.root / "artifacts" / "release_truth"

    def run(self, run_id: str = "") -> dict:
        """Run full release truth capture."""
        if not run_id:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        results = {"run_id": run_id, "artifacts": {}}

        # Git info
        results["artifacts"]["git_commit"] = self._capture(run_dir, "git_commit.txt",
            ["git", "rev-parse", "HEAD"])
        results["artifacts"]["git_status"] = self._capture(run_dir, "git_status_porcelain.txt",
            ["git", "status", "--porcelain"])

        # Environment
        results["artifacts"]["python_version"] = self._capture(run_dir, "python_version.txt",
            [sys.executable, "--version"])
        results["artifacts"]["platform"] = self._capture(run_dir, "platform.txt",
            [sys.executable, "-c", "import platform; print(platform.platform())"])

        # Dependencies
        results["artifacts"]["dependency_lock_hash"] = self._capture_hash(run_dir,
            "dependency_lock_hash.txt", self._find_lock_files())

        # Test collection and execution
        test_json = self._run_tests(run_dir)
        results["artifacts"]["test_collection"] = str(test_json.get("collection_file", ""))
        results["artifacts"]["test_summary"] = str(test_json.get("summary_file", ""))
        results["artifacts"]["pytest_output"] = str(test_json.get("output_file", ""))

        # Quarantine
        results["artifacts"]["quarantine_manifest_hash"] = self._capture_hash(run_dir,
            "quarantine_manifest_hash.txt", [self._find_quarantine()])

        # Data manifests
        results["artifacts"]["data_manifest_hashes"] = self._capture_data_manifests(run_dir)

        # Full bundle hash
        results["artifacts"]["full_bundle_hash"] = self._capture_bundle_hash(run_dir)

        # Save results
        (run_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))

        return results

    def _capture(self, run_dir: Path, filename: str, cmd: list) -> str:
        """Run command and capture output."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=self.root)
            output = result.stdout.strip()
            (run_dir / filename).write_text(output)
            return output
        except Exception as e:
            error = f"ERROR: {e}"
            (run_dir / filename).write_text(error)
            return error

    def _capture_hash(self, run_dir: Path, filename: str, files: list) -> str:
        """Hash multiple files into one digest."""
        h = hashlib.sha256()
        for f in files:
            p = Path(f)
            if p.exists():
                h.update(p.read_bytes())
        digest = h.hexdigest()
        (run_dir / filename).write_text(digest)
        return digest

    def _run_tests(self, run_dir: Path) -> dict:
        """Run pytest and capture results."""
        output_file = run_dir / "pytest_output.txt"
        collection_file = run_dir / "test_collection.json"
        summary_file = run_dir / "test_summary.json"
        collect_command_file = run_dir / "collect_command.txt"
        pytest_command_file = run_dir / "pytest_command.txt"
        collect_cmd = [
            sys.executable, "-m", "pytest", "--collect-only", "-q",
            "graxia/packages/quant_os/tests/",
        ]
        pytest_cmd = [
            sys.executable, "-m", "pytest", "-q", "--tb=line",
            "graxia/packages/quant_os/tests/",
        ]
        collect_command_file.write_text(" ".join(collect_cmd))
        pytest_command_file.write_text(" ".join(pytest_cmd))

        # Run collection
        try:
            result = subprocess.run(
                collect_cmd,
                capture_output=True, text=True, timeout=300, cwd=self.root
            )
            collection_file.write_text(result.stdout)
        except Exception as e:
            collection_file.write_text(f"ERROR: {e}")

        # Run tests
        try:
            result = subprocess.run(
                pytest_cmd,
                capture_output=True, text=True, timeout=600, cwd=self.root
            )
            output_file.write_text(result.stdout + result.stderr)

            # Parse summary
            summary = {
                "return_code": result.returncode,
                "output_lines": len(result.stdout.splitlines()),
            }
            summary_file.write_text(json.dumps(summary, indent=2))
        except Exception as e:
            output_file.write_text(f"ERROR: {e}")
            summary_file.write_text(json.dumps({"error": str(e)}))

        return {
            "collection_file": collection_file,
            "summary_file": summary_file,
            "output_file": output_file,
        }

    def _find_lock_files(self) -> list:
        """Find dependency lock files."""
        candidates = [
            "requirements.txt", "requirements.lock",
            "pyproject.toml", "setup.cfg",
        ]
        return [str(self.root / f) for f in candidates if (self.root / f).exists()]

    def _find_quarantine(self) -> str:
        """Find quarantine manifest."""
        path = self.root / "graxia" / "packages" / "quant_os" / "quarantine_manifest.json"
        return str(path) if path.exists() else ""

    def _capture_data_manifests(self, run_dir: Path) -> str:
        """Hash all data manifests."""
        manifests_dir = self.root / "graxia" / "packages" / "quant_os" / "data" / "manifests"
        if not manifests_dir.exists():
            return "{}"

        h = hashlib.sha256()
        for f in sorted(manifests_dir.glob("*.json")):
            h.update(f.read_bytes())

        digest = h.hexdigest()
        (run_dir / "data_manifest_hashes.txt").write_text(digest)
        return digest

    def _capture_bundle_hash(self, run_dir: Path) -> str:
        """Hash all artifacts in the run directory."""
        h = hashlib.sha256()
        for f in sorted(run_dir.iterdir()):
            if f.is_file() and f.name != "full_bundle_hash.txt":
                h.update(f.read_bytes())
        digest = h.hexdigest()
        (run_dir / "full_bundle_hash.txt").write_text(digest)
        return digest


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    runner = ReleaseTruthRunner(root)
    result = runner.run()
    print(json.dumps(result, indent=2, default=str))
