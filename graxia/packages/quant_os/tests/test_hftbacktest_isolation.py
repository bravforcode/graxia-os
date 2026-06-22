"""G0.1.3: Verify hftbacktest is quarantined and not imported by canonical package."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")

def test_no_hftbacktest_imports_in_canonical():
    """Canonical package must not import hftbacktest."""
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import graxia.packages.quant_os;"
        ],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, f"Import failed: {result.stderr}"
    # Also check source files directly
    import re
    quant_os_dir = REPO_ROOT / "graxia" / "packages" / "quant_os"
    violations = []
    for py_file in quant_os_dir.rglob("*.py"):
        if "quarantine" in str(py_file).lower() or "test_hftbacktest" in py_file.name:
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'\bhftbacktest\b', content):
            violations.append(str(py_file.relative_to(quant_os_dir)))
    assert not violations, f"hftbacktest referenced in: {violations}"

def test_hftbacktest_quarantine_manifest_exists():
    """Quarantine manifest must exist with correct upstream SHA."""
    manifest = REPO_ROOT / "graxia" / "packages" / "quant_os" / "repo_intelligence" / "registry" / "quarantine_hftbacktest.json"
    assert manifest.exists(), f"Missing: {manifest}"
    import json
    data = json.loads(manifest.read_text())
    assert data["upstream_commit_sha"] == "5f3ec40b2afb764e0fea112f941ed85523ef4e88"
    assert len(data["dirty_diff_sha256"]) == 64  # SHA-256 hex length
