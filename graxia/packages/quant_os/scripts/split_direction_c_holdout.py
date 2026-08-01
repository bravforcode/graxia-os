"""Split Direction C sacred holdout from BTC/ETH data."""
import csv
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BTC_FILE = PROJECT_ROOT / "data" / "BTCUSD_D1.csv"
ETH_FILE = PROJECT_ROOT / "data" / "ETHUSD_D1.csv"
HOLDOUT_DIR = PROJECT_ROOT / "data" / "sacred_holdout"
RESEARCH_DIR = PROJECT_ROOT / "data" / "direction_c"

def load_csv(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "date": row["time"].split(" ")[0],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                })
            except (ValueError, KeyError):
                continue
    return rows

print("Loading BTC...")
btc = load_csv(BTC_FILE)
print(f"  BTC: {len(btc)} rows ({btc[0]['date']} -> {btc[-1]['date']})")

print("Loading ETH...")
eth = load_csv(ETH_FILE)
print(f"  ETH: {len(eth)} rows ({eth[0]['date']} -> {eth[-1]['date']})")

# Sacred holdout: last 12 months (2025-07-01 to 2026-06-29)
holdout_start = "2025-07-01"
btc_holdout = [r for r in btc if r["date"] >= holdout_start]
btc_research = [r for r in btc if r["date"] < holdout_start]
eth_holdout = [r for r in eth if r["date"] >= holdout_start]
eth_research = [r for r in eth if r["date"] < holdout_start]

print(f"\nBTC Holdout: {len(btc_holdout)} rows ({btc_holdout[0]['date']} -> {btc_holdout[-1]['date']})")
print(f"BTC Research: {len(btc_research)} rows ({btc_research[0]['date']} -> {btc_research[-1]['date']})")
print(f"ETH Holdout: {len(eth_holdout)} rows ({eth_holdout[0]['date']} -> {eth_holdout[-1]['date']})")
print(f"ETH Research: {len(eth_research)} rows ({eth_research[0]['date']} -> {eth_research[-1]['date']})")

# Write files
HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

fields = ["date", "open", "high", "low", "close", "volume"]

# BTC holdout
with open(HOLDOUT_DIR / "holdout_btc.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(btc_holdout)

# BTC research
with open(RESEARCH_DIR / "btc_research.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(btc_research)

# ETH research (aligned to BTC dates)
btc_dates = {r["date"] for r in btc_research}
eth_aligned = [r for r in eth_research if r["date"] in btc_dates]
with open(RESEARCH_DIR / "eth_research.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(eth_aligned)

print(f"\nFiles created:")
print(f"  Sacred holdout: {HOLDOUT_DIR / 'holdout_btc.csv'} ({len(btc_holdout)} rows)")
print(f"  BTC research: {RESEARCH_DIR / 'btc_research.csv'} ({len(btc_research)} rows)")
print(f"  ETH research: {RESEARCH_DIR / 'eth_research.csv'} ({len(eth_aligned)} rows)")
print(f"\n!!! DO NOT TOUCH holdout_btc.csv UNTIL PHASE 4.5 !!!")

# Verify volume
btc_vol_ok = sum(1 for r in btc_research if r["volume"] > 0)
eth_vol_ok = sum(1 for r in eth_aligned if r["volume"] > 0)
print(f"\nVolume check:")
print(f"  BTC: {btc_vol_ok}/{len(btc_research)} bars have volume > 0")
print(f"  ETH: {eth_vol_ok}/{len(eth_aligned)} bars have volume > 0")
