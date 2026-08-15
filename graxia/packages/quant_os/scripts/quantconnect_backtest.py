"""
QuantConnect Backtest Runner — Run backtest on QuantConnect cloud.

Usage:
    python scripts/quantconnect_backtest.py --project-id <id> --start 2020-01-01 --end 2026-01-01

Prerequisites:
    1. Install LEAN CLI: pip install lean
    2. Configure QuantConnect credentials: lean config set "job-user-id" "your-id"
    3. Create project on QuantConnect: lean project create "QuantOS-Bridge" Python
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_backtest(project_id: int, start_date: str, end_date: str, output_dir: str):
    """Run backtest on QuantConnect."""
    print(f"Running backtest on QuantConnect...")
    print(f"  Project ID: {project_id}")
    print(f"  Start date: {start_date}")
    print(f"  End date: {end_date}")
    print(f"  Output: {output_dir}")
    print()

    # Run backtest using LEAN CLI
    cmd = [
        "lean", "backtest",
        str(project_id),
        "--output", output_dir,
        "--start-date", start_date,
        "--end-date", end_date,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    print(f"Backtest completed successfully!")
    print(f"Results saved to: {output_dir}")

    # Parse results
    results_file = Path(output_dir) / "backtest-results.json"
    if results_file.exists():
        with open(results_file, "r") as f:
            results = json.load(f)

        print(f"\nBacktest Results:")
        print(f"  Sharpe Ratio: {results.get('sharpeRatio', 'N/A')}")
        print(f"  Max Drawdown: {results.get('maxDrawdown', 'N/A')}")
        print(f"  Total Trades: {results.get('totalOrders', 'N/A')}")
        print(f"  Win Rate: {results.get('winRate', 'N/A')}")

    return True


def deploy_live(project_id: int, brokerage: str, node: str):
    """Deploy to live trading on QuantConnect."""
    print(f"Deploying to live trading...")
    print(f"  Project ID: {project_id}")
    print(f"  Brokerage: {brokerage}")
    print(f"  Node: {node}")
    print()

    # Deploy using LEAN CLI
    cmd = [
        "lean", "live",
        str(project_id),
        "--brokerage", brokerage,
        "--node", node,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    print(f"Deployed successfully!")
    return True


def main():
    parser = argparse.ArgumentParser(description="QuantConnect Backtest Runner")
    parser.add_argument("--project-id", type=int, required=True, help="QuantConnect project ID")
    parser.add_argument("--start", type=str, default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, default="artifacts/quantconnect", help="Output directory")
    parser.add_argument("--deploy", action="store_true", help="Deploy to live trading")
    parser.add_argument("--brokerage", type=str, default="QuantConnectPaperTrading", help="Brokerage name")
    parser.add_argument("--node", type=str, default="live", help="Node name")

    args = parser.parse_args()

    # Create output directory
    Path(args.output).mkdir(parents=True, exist_ok=True)

    if args.deploy:
        success = deploy_live(args.project_id, args.brokerage, args.node)
    else:
        success = run_backtest(args.project_id, args.start, args.end, args.output)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
