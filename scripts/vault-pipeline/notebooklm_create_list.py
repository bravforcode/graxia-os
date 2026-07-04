"""
notebooklm_create_list.py — Shows what notebooks to create on NotebookLM
Run this first, then create notebooks on website, then run notebooklm_register_url.py
"""

from pathlib import Path
import os

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"

# Map notebook categories to vault folders
NOTEBOOKS = [
    ("Strategy BOS/CHOCH", "skills/trading/strategies/bos_choch.md"),
    ("Strategy EMA Cross", "skills/trading/strategies/ema_cross.md"),
    ("Strategy FVG", "skills/trading/strategies/fair_value_gap.md"),
    ("Strategy Liquidity Sweep", "skills/trading/strategies/liquidity_sweep.md"),
    ("Strategy Order Block", "skills/trading/strategies/order_block.md"),
    ("Strategy Fibonacci", "skills/trading/strategies/fibonacci.md"),
    ("Strategy London Breakout", "skills/trading/strategies/london_breakout.md"),
    ("Strategy Opening Range", "skills/trading/strategies/opening_range.md"),
    ("Strategy VWAP Rejection", "skills/trading/strategies/vwap_rejection.md"),
    ("Strategy Multi-TF Align", "skills/trading/strategies/multi_tf_align.md"),
    ("Strategy News Fade", "skills/trading/strategies/news_fade.md"),
    ("Strategy Supply/Demand", "skills/trading/strategies/supply_demand.md"),
    ("Strategy RSI Divergence", "skills/trading/strategies/rsi_divergence.md"),
    ("Backtest XAUUSD", "03-resources/trading/backtest/"),
    ("Backtest EURUSD", "03-resources/trading/backtest/"),
    ("Macro Dashboard", "03-resources/trading/macro/"),
    ("ML Models", "03-resources/trading/models/"),
    ("Trade Journal", "07-Daily/trades/"),
    ("Risk Dashboard", "03-resources/trading/risk/"),
    ("Regime Detection", "03-resources/trading/regime/"),
]

print("=" * 60)
print("  NOTEBOOKS TO CREATE ON NOTEBOOKLM")
print("=" * 60)
print()
print("Go to: https://notebooklm.google.com/")
print("Create each notebook, then copy its URL.")
print()
print("After creating all, run:")
print("  python notebooklm_register_url.py")
print()

# Check which sources exist
for i, (name, path) in enumerate(NOTEBOOKS, 1):
    full = VAULT / path
    if full.is_dir():
        count = len(list(full.glob("*.md")))
        status = f"({count} sources)"
    elif full.is_file():
        size = full.stat().st_size
        status = f"({size} bytes)"
    else:
        status = "(missing)"
    print(f"  {i:2d}. {name:<30s} {status}")

print()
print("=" * 60)
print(f"  Total: {len(NOTEBOOKS)} notebooks")
print("=" * 60)
