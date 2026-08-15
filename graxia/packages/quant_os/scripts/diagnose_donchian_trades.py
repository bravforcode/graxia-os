"""Diagnostic: test Donchian with different parameters to find trade-generating configs."""

import csv
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant_os.backtest.engine import BacktestConfig, BacktestEngine
from quant_os.strategies.donchian import DonchianBreakout

# Load data
csv_path = ROOT / "data" / "XAUUSD_D1.csv"
data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            vol = float(row.get("volume", "0"))
            if vol == 0:
                continue
            data["open"].append(float(row["open"]))
            data["high"].append(float(row["high"]))
            data["low"].append(float(row["low"]))
            data["close"].append(float(row["close"]))
            data["volume"].append(int(vol))
        except (ValueError, KeyError):
            continue

print(f"Loaded {len(data['close'])} bars")
print(f"Price range: {min(data['close']):.2f} - {max(data['close']):.2f}")
print(f"First price: {data['close'][0]:.2f}, Last price: {data['close'][-1]:.2f}")

ts = [datetime(2000, 1, 3, tzinfo=UTC) + timedelta(days=i) for i in range(len(data["close"]))]

# Test different configs
configs = [
    {"period": 10, "vol_filter": False, "label": "P10_noVOL"},
    {"period": 15, "vol_filter": False, "label": "P15_noVOL"},
    {"period": 20, "vol_filter": False, "label": "P20_noVOL"},
    {"period": 20, "vol_filter": True, "label": "P20_VOL07"},
    {"period": 25, "vol_filter": False, "label": "P25_noVOL"},
    {"period": 30, "vol_filter": False, "label": "P30_noVOL"},
    {"period": 50, "vol_filter": False, "label": "P50_noVOL"},
    {"period": 20, "vol_filter": True, "vol_pctile": 0.5, "label": "P20_VOL05"},
]

for cfg in configs:
    strat = DonchianBreakout(
        period=cfg["period"],
        atr_period=14,
        atr_sl_mult=2.0,
        atr_tp_mult=3.0,
        vol_filter=cfg["vol_filter"],
        vol_filter_pctile=cfg.get("vol_pctile", 0.7),
    )
    config = BacktestConfig(
        initial_capital=Decimal("10000"),
        spread_pips=0.3,
        slippage_pips=0.1,
        commission_per_lot=Decimal("0.0"),
        risk_per_trade_bps=100,
        strict_mtf=False,
        enable_swap=False,
    )
    engine = BacktestEngine(config=config)
    engine._symbol = "XAUUSD"  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strat)
    engine.load_data(data, ts)
    result = engine.run()
    metrics = result["metrics"]
    trades = result.get("trades", [])

    # Count buy vs sell trades
    buys = sum(1 for t in trades if t.get("side") == "LONG")
    sells = sum(1 for t in trades if t.get("side") == "SHORT")

    print(
        f"{cfg['label']:20s}: trades={len(trades):4d} (B:{buys} S:{sells}), "
        f"PnL=${float(metrics.total_pnl):10.2f}, "
        f"sharpe={metrics.sharpe_ratio:7.3f}, "
        f"winrate={metrics.win_rate*100:5.1f}%, "
        f"maxDD={metrics.max_drawdown_pct:5.1f}%, "
        f"PF={metrics.profit_factor:.2f}"
    )
