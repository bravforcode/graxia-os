"""G0.5: Verify canonical backtest config can be created in a fresh process."""
import subprocess
import sys

REPO_ROOT = r"C:\Users\menum\graxia os"


def test_canonical_config_instantiate():
    """RiskPolicy must instantiate with bps-based config in a fresh process."""
    code = """
from graxia.packages.quant_os.risk.risk_policy import RiskPolicy
p = RiskPolicy(
    max_daily_loss_bps=50,
    max_weekly_loss_bps=150,
    max_total_drawdown_bps=300,
    max_open_positions=1,
    risk_per_trade_bps=10,
)
print(f"OK:{p.risk_per_trade_bps}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"Instantiation failed (rc={result.returncode}):\n{result.stderr}"
    assert "OK:10" in result.stdout, f"Unexpected stdout: {result.stdout}"
