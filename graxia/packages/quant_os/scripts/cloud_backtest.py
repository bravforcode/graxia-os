"""Cloud Backtest Runner — run LEAN algorithms on QuantConnect cloud.

Usage:
    # Run local backtest with cloud data
    python scripts/cloud_backtest.py --algo QuantOS-Bridge --start 2020-01-01 --end 2025-01-01

    # Run cloud backtest on QC servers
    python scripts/cloud_backtest.py --algo QuantOS-Bridge --cloud --start 2020-01-01

    # Deploy to paper trading
    python scripts/cloud_backtest.py --algo QuantOS-Bridge --deploy

    # Verify all data providers
    python scripts/cloud_backtest.py --verify

Prerequisites:
    1. Set QUANTCONNECT_USER_ID + QUANTCONNECT_API_TOKEN in .env
    2. Install LEAN CLI: pip install lean
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QC_WORKSPACE = PROJECT_ROOT / "quantconnect" / "qc_workspace"
ALGO_DIR = QC_WORKSPACE / "QuantOS-Bridge"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "quantconnect"


def _run(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 300) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(cwd or PROJECT_ROOT), timeout=timeout
    )
    return result.returncode, result.stdout, result.stderr


def verify_providers():
    """Verify all configured data providers."""
    print("=" * 60)
    print("Data Provider Verification")
    print("=" * 60)

    # Load .env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    sys.path.insert(0, str(PROJECT_ROOT))
    from market_data.providers import DataProviders
    providers = DataProviders.from_env()

    if not providers._providers:
        print("\n[!] No data providers configured.")
        print("    Set API keys in .env — see .env.example for template.")
        _print_signup_links()
        return False

    results = providers.health_check()
    all_ok = True
    for r in results:
        status = "OK" if r.get("ok") else "FAILED"
        icon = "+" if r.get("ok") else "x"
        print(f"  [{icon}] {r['provider']:15s} {status}")
        if not r.get("ok"):
            all_ok = False
            if "error" in r:
                print(f"      Error: {r['error']}")

    providers.close()

    print()
    if all_ok:
        print("[+] All providers healthy!")
    else:
        print("[!] Some providers failed — check credentials in .env")

    return all_ok


def run_local_backtest(algo_name: str, start: str, end: str, output: str):
    """Run backtest locally using LEAN Docker with cloud data."""
    print(f"Running local backtest: {algo_name}")
    print(f"  Period: {start} to {end}")
    print(f"  Output: {output}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    algo_path = QC_WORKSPACE / algo_name
    if not algo_path.exists():
        print(f"[!] Algorithm not found: {algo_path}")
        print("    Available algorithms:")
        for d in QC_WORKSPACE.iterdir():
            if d.is_dir() and (d / "main.py").exists():
                print(f"      - {d.name}")
        return False

    cmd = [
        "lean", "backtest",
        str(algo_path),
        "--output", str(OUTPUT_DIR),
        "--start-date", start,
        "--end-date", end,
    ]

    print(f"  Command: {' '.join(cmd)}")
    print()

    rc, stdout, stderr = _run(cmd, timeout=1800)  # 30 min timeout
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    if rc == 0:
        print(f"\n[+] Backtest completed! Results in: {OUTPUT_DIR}")
        _print_backtest_summary(OUTPUT_DIR)
    else:
        print(f"\n[x] Backtest failed with exit code {rc}")

    return rc == 0


def run_cloud_backtest(algo_name: str, start: str, end: str):
    """Run backtest on QuantConnect cloud servers."""
    print(f"Running cloud backtest: {algo_name}")
    print(f"  Period: {start} to {end}")
    print()

    # Check credentials
    user_id = os.getenv("QUANTCONNECT_USER_ID", "")
    api_token = os.getenv("QUANTCONNECT_API_TOKEN", "")
    if not api_token:
        print("[!] QUANTCONNECT_API_TOKEN not set in .env")
        print("    Get your token: https://www.quantconnect.com/account")
        return False

    algo_path = QC_WORKSPACE / algo_name
    if not algo_path.exists():
        print(f"[!] Algorithm not found: {algo_path}")
        return False

    # Push code to cloud first
    print("  Pushing algorithm to cloud...")
    rc, stdout, stderr = _run(["lean", "project", "push", str(algo_path)])
    if rc != 0:
        print(f"  [!] Push failed: {stderr}")
        return False
    print(f"  [+] Pushed: {stdout.strip()}")

    # Run backtest
    print("  Starting cloud backtest...")
    cmd = [
        "lean", "backtest",
        str(algo_path),
        "--start-date", start,
        "--end-date", end,
    ]

    rc, stdout, stderr = _run(cmd, timeout=3600)  # 60 min for cloud
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    return rc == 0


def deploy_paper_trading(algo_name: str):
    """Deploy algorithm to QuantConnect paper trading."""
    print(f"Deploying to paper trading: {algo_name}")

    algo_path = QC_WORKSPACE / algo_name
    if not algo_path.exists():
        print(f"[!] Algorithm not found: {algo_path}")
        return False

    # Push first
    print("  Pushing algorithm...")
    rc, stdout, stderr = _run(["lean", "project", "push", str(algo_path)])
    if rc != 0:
        print(f"  [!] Push failed: {stderr}")
        return False

    # Deploy
    print("  Deploying to live paper trading...")
    cmd = [
        "lean", "live",
        str(algo_path),
        "--brokerage", "QuantConnect Paper Trading",
        "--data-feed", "QuantConnect Live Data",
    ]

    rc, stdout, stderr = _run(cmd, timeout=600)
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    return rc == 0


def _print_backtest_summary(output_dir: Path):
    """Print backtest results summary."""
    results_file = output_dir / "backtest-results.json"
    if results_file.exists():
        with open(results_file) as f:
            data = json.load(f)
        stats = data.get("statistics", {})
        print("\n--- Backtest Results ---")
        print(f"  Sharpe Ratio:     {stats.get('sharpeRatio', 'N/A')}")
        print(f"  Max Drawdown:     {stats.get('maxDrawdown', 'N/A')}")
        print(f"  Total Trades:     {stats.get('totalOrders', 'N/A')}")
        print(f"  Win Rate:         {stats.get('winRate', 'N/A')}")
        print(f"  Net Profit:       {stats.get('netProfit', 'N/A')}")
        print(f"  Annual Return:    {stats.get('compoundingAnnualReturnValue', 'N/A')}")
    else:
        # Check for summary file
        for f in output_dir.glob("*-summary.json"):
            with open(f) as fh:
                data = json.load(fh)
            print(f"\n--- {f.stem} ---")
            for k, v in list(data.items())[:10]:
                print(f"  {k}: {v}")


def _print_signup_links():
    """Print signup links for all providers."""
    print("\n  Signup Links:")
    print("  " + "-" * 50)
    print("  QuantConnect:  https://www.quantconnect.com/signup")
    print("    → Get API token: https://www.quantconnect.com/account")
    print()
    print("  Oanda:         https://www.oanda.com/account/practice/")
    print("    → Get API token: https://www.oanda.com/account/api-access")
    print()
    print("  Polygon.io:    https://polygon.io/")
    print("    → Get API key: https://dashboard.polygon.io/")
    print()
    print("  Alpha Vantage: https://www.alphavantage.co/support/#api-key")
    print("    → Free tier: 25 req/day, 5/min")
    print()
    print("  Add keys to: .env (see .env.example for template)")


def list_algorithms():
    """List available algorithms."""
    print("Available algorithms:")
    print()
    for d in sorted(QC_WORKSPACE.iterdir()):
        if d.is_dir() and (d / "main.py").exists():
            algo_file = d / "main.py"
            with open(algo_file) as f:
                first_lines = [line for line in f.readlines()[:5] if line.strip() and not line.startswith("#")]
            desc = first_lines[0].strip() if first_lines else "(no description)"
            print(f"  {d.name:30s} {desc}")


def main():
    parser = argparse.ArgumentParser(description="Cloud Backtest Runner")
    parser.add_argument("--algo", type=str, default="QuantOS-Bridge", help="Algorithm name")
    parser.add_argument("--start", type=str, default="2020-01-01", help="Start date")
    parser.add_argument("--end", type=str, default="2025-01-01", help="End date")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR), help="Output directory")
    parser.add_argument("--cloud", action="store_true", help="Run on QC cloud instead of local")
    parser.add_argument("--deploy", action="store_true", help="Deploy to paper trading")
    parser.add_argument("--verify", action="store_true", help="Verify data providers")
    parser.add_argument("--list", action="store_true", help="List available algorithms")

    args = parser.parse_args()

    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    if args.verify:
        verify_providers()
    elif args.list:
        list_algorithms()
    elif args.deploy:
        deploy_paper_trading(args.algo)
    elif args.cloud:
        run_cloud_backtest(args.algo, args.start, args.end)
    else:
        run_local_backtest(args.algo, args.start, args.end, args.output)


if __name__ == "__main__":
    main()
