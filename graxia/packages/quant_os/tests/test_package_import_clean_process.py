"""G0.5: Verify quant_os imports cleanly in a fresh process."""
import subprocess
import sys

REPO_ROOT = r"C:\Users\menum\graxia os"


def test_package_import_clean_process():
    """import graxia.packages.quant_os must succeed in a fresh Python process."""
    code = "import graxia.packages.quant_os; print('OK')"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"Import failed (rc={result.returncode}):\n{result.stderr}"
    assert "OK" in result.stdout, f"Unexpected stdout: {result.stdout}"


def test_risk_policy_import_clean_process():
    """import RiskPolicy from the canonical bps-based module must succeed."""
    code = "from graxia.packages.quant_os.risk.risk_policy import RiskPolicy; print('OK')"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"Import failed (rc={result.returncode}):\n{result.stderr}"
    assert "OK" in result.stdout
