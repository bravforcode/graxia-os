"""Sacred Holdout: Run BTCUSD H1 donchian on never-seen data.

Pre-registered criteria (written BEFORE running):
1. OOS Sharpe > 0.5
2. OOS Win rate > 45%
3. OOS Max drawdown < 20%
4. OOS Total P&L > $0
5. OOS Trades >= 30
"""
import csv
import json
import os
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np
import pandas as pd

from paper_engine.campaign import CampaignConfig, get_spread_bps
from paper_engine.engine import (
    _get_strategy,
    _simulate_trades,
    _trades_per_year,
    CampaignResult,
)

HOLDOUT_FILE = _project_root / "data" / "sacred_holdout" / "holdout_btc.csv"
REPORTS = _project_root / "reports" / "paper_engine"


def load_holdout_data() -> pd.DataFrame:
    """Load sacred holdout BTC data."""
    rows = []
    with open(HOLDOUT_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    # Ensure we have OHLCV (lowercase, as expected by strategies)
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")

    if "volume" not in df.columns:
        df["volume"] = 0

    # Convert to numeric
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def main():
    print("=" * 60)
    print("SACRED HOLDOUT: BTCUSD H1 Donchian")
    print("=" * 60)
    print()

    # 1. Load holdout data
    print("Loading sacred holdout data...")
    df = load_holdout_data()
    print(f"  Rows: {len(df)}")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  Close range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    print()

    # 2. Configure campaign
    config = CampaignConfig(
        campaign_id="holdout_BTCUSD_H1_donchian",
        strategy_id="donchian",
        symbol="BTCUSD",
        timeframe="H1",
        spread_bps=get_spread_bps("BTCUSD"),
        params={"period": 20, "vol_filter": True},
    )

    print(f"Campaign: {config.campaign_id}")
    print(f"Strategy: {config.strategy_id}")
    print(f"Symbol: {config.symbol}")
    print(f"Spread: {config.spread_bps} bps")
    print(f"Params: {config.params}")
    print()

    # 3. Run strategy
    print("Running donchian strategy...")
    strategy = _get_strategy(config.strategy_id)
    strategy_result = strategy.generate_signals(df, config.params)
    print(f"  Signals generated: {len(strategy_result.signals)}")
    print()

    # 4. Simulate trades
    print("Simulating trades with real spread costs...")
    trades, equity_curve = _simulate_trades(strategy_result, df, config)
    print(f"  Trades executed: {len(trades)}")
    print()

    if not trades:
        print("ERROR: No trades generated on holdout data")
        return

    # 5. Compute metrics
    pnls = np.array([t.net_pnl for t in trades])
    returns = pnls / 100000
    tpy = _trades_per_year(trades)

    # Sharpe
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(tpy)) if np.std(returns) > 1e-10 else 0.0

    # Win rate
    wins = pnls > 0
    win_rate = float(np.mean(wins)) * 100

    # Max drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
    max_dd_pct = float(max_dd / 100000 * 100)

    # Profit factor
    gross_profit = float(np.sum(pnls[wins])) if np.any(wins) else 0.0
    gross_loss = float(np.sum(pnls[~wins])) if np.any(~wins) else 0.0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float("inf")

    # Total P&L
    total_pnl = float(np.sum(pnls))

    # Average win/loss
    avg_win = float(np.mean(pnls[wins])) if np.any(wins) else 0.0
    avg_loss = float(np.mean(pnls[~wins])) if np.any(~wins) else 0.0

    print("=" * 60)
    print("HOLDOUT RESULTS")
    print("=" * 60)
    print()
    print(f"  Total trades:      {len(trades)}")
    print(f"  TPY:               {tpy:.1f}")
    print(f"  Sharpe ratio:      {sharpe:.4f}")
    print(f"  Win rate:          {win_rate:.1f}%")
    print(f"  Profit factor:     {profit_factor:.2f}")
    print(f"  Total P&L:         ${total_pnl:,.2f}")
    print(f"  Max drawdown:      ${max_dd:,.2f} ({max_dd_pct:.1f}%)")
    print(f"  Avg win:           ${avg_win:,.2f}")
    print(f"  Avg loss:          ${avg_loss:,.2f}")
    print()

    # 6. Check pre-registered criteria
    print("=" * 60)
    print("PRE-REGISTERED CRITERIA CHECK")
    print("=" * 60)
    print()

    criteria = [
        ("OOS Sharpe > 0.5", sharpe > 0.5, f"{sharpe:.4f}"),
        ("OOS Win rate > 45%", win_rate > 45, f"{win_rate:.1f}%"),
        ("OOS Max DD < 20%", max_dd_pct < 20, f"{max_dd_pct:.1f}%"),
        ("OOS Total P&L > $0", total_pnl > 0, f"${total_pnl:,.2f}"),
        ("OOS Trades >= 30", len(trades) >= 30, f"{len(trades)}"),
    ]

    all_pass = True
    for name, passed, value in criteria:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {value}")
        if not passed:
            all_pass = False

    print()
    print("=" * 60)
    if all_pass:
        print("VERDICT: PASS - Candidate survives sacred holdout")
    else:
        print("VERDICT: FAIL - Candidate rejected at sacred holdout")
    print("=" * 60)
    print()

    # 7. Save results
    output = {
        "campaign_id": config.campaign_id,
        "strategy": config.strategy_id,
        "symbol": config.symbol,
        "timeframe": config.timeframe,
        "spread_bps": config.spread_bps,
        "params": config.params,
        "holdout_period": "%s to %s" % (df.index[0], df.index[-1]),
        "holdout_rows": len(df),
        "total_trades": len(trades),
        "tpy": round(tpy, 1),
        "sharpe": round(sharpe, 4),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "total_pnl": round(total_pnl, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "criteria": {name: {"passed": passed, "value": value} for name, passed, value in criteria},
        "verdict": "PASS" if all_pass else "FAIL",
    }

    output_path = REPORTS / "holdout_result.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Results saved to {output_path}")

    # 8. Trade log (first 10)
    print()
    print("Sample trades (first 10):")
    print("-" * 80)
    print("%-20s %-6s %-10s %-10s %-10s %-10s" % ("Entry", "Dir", "Entry$", "Exit$", "P&L", "Reason"))
    print("-" * 80)
    for t in trades[:10]:
        direction = "LONG" if t.direction == 1 else "SHORT"
        print("%-20s %-6s %-10.2f %-10.2f %-10.2f %-10s" % (
            t.entry_time[:19] if t.entry_time else "N/A",
            direction,
            t.entry_price or 0,
            t.exit_price or 0,
            t.net_pnl,
            t.exit_reason or "N/A",
        ))
    print("-" * 80)


if __name__ == "__main__":
    main()
