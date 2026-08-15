"""
Calendar Effects + Strategy Enhancement Scanner
Tests: day-of-week, month-of-year, turn-of-month, and
strategy enhancement (Donchian + filters).
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json
from datetime import datetime

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA = BASE / "data" / "EURUSD_D1_clean.csv"
COST = 3.4
TRAIN = 0.80
WARMUP = 200


def sharpe_from_returns(rets):
    if len(rets) < 5: return 0, 0
    avg = np.mean(rets)
    std = np.std(rets, ddof=1)
    return float(avg / (std + 1e-10) * np.sqrt(252)), float(avg * 252 * 100)


def eval_strategy(opens, closes, signals):
    """Simulate always-in strategy, return OOS returns."""
    n = len(closes)
    sp = int(n * TRAIN)
    pos, entry_px = 0, 0.0
    trades = []
    for i in range(WARMUP, n):
        bar = "OOS" if i >= sp else "IS"
        sig = signals[i]
        if pos == 0 and sig != 0:
            ei = i + 1 if i + 1 < n else i
            entry_px = opens[ei] if i + 1 < n else closes[i]
            pos = sig
        elif pos != 0 and sig != pos:
            ei = i + 1 if i + 1 < n else i
            exit_px = opens[ei] if i + 1 < n else closes[i]
            r = (exit_px - entry_px) / entry_px if pos == 1 else (entry_px - exit_px) / entry_px
            if bar == "OOS":
                trades.append(r - COST / 10000.0)
            pos = 0
            if sig != 0:
                entry_px = exit_px
                pos = sig
    return trades


def donchian_signals(highs, lows, closes, period):
    n = len(closes)
    sigs = np.zeros(n, dtype=int)
    pos = 0
    for i in range(period, n):
        hh = np.max(highs[max(0, i - period) : i])
        ll = np.min(lows[max(0, i - period) : i])
        if closes[i] > hh: pos = 1
        elif closes[i] < ll: pos = -1
        sigs[i] = pos
    return sigs


def calendar_filter(dates, sigs, rule, rule_arg):
    """Filter signals to only execute on specific calendar days.
    rule: 'dow' (day of week), 'month', 'tom' (turn of month), 'first_N' (first N days of month)"""
    n = len(sigs)
    filtered = np.zeros(n, dtype=int)
    pos = 0

    for i in range(n):
        dt = dates[i]
        if isinstance(dt, str):
            dt = pd.Timestamp(dt)

        allowed = True
        if rule == "dow":
            allowed = (dt.dayofweek == rule_arg)  # 0=Mon, 4=Fri
        elif rule == "month":
            allowed = (dt.month == rule_arg)
        elif rule == "tom":
            # Turn of month: last 3 + first 3 trading days
            # We approximate: day <= 3 or day >= (days_in_month - 2)
            last_day = pd.Timestamp(year=dt.year, month=dt.month, day=1) + pd.offsets.MonthEnd(1)
            days_left = (last_day - dt).days
            allowed = (dt.day <= 3 or days_left <= 2)
        elif rule == "mid_month":
            allowed = (10 <= dt.day <= 20)
        elif rule == "not_mid":
            allowed = not (10 <= dt.day <= 20)

        if allowed:
            if sigs[i] != 0:
                pos = sigs[i]
        filtered[i] = pos if allowed else 0  # flat when not allowed

    return filtered


def vol_filter(sigs, closes, min_atr_ratio):
    """Only trade when recent volatility is above threshold."""
    n = len(closes)
    atr = np.zeros(n)
    for i in range(14, n):
        if i == 14:
            atr[i] = closes[i] - closes[i - 1]  # rough init
        else:
            tr = abs(closes[i] - closes[i - 1])
            atr[i] = (atr[i - 1] * 13 + tr) / 14 if atr[i - 1] else tr

    atr_ratio = atr / closes
    med_ratio = np.nanmedian(atr_ratio[200:])

    filtered = np.zeros(n, dtype=int)
    pos = 0
    for i in range(n):
        if atr_ratio[i] > med_ratio * min_atr_ratio or np.isnan(atr_ratio[i]):
            if sigs[i] != 0:
                pos = sigs[i]
            filtered[i] = pos
        else:
            filtered[i] = 0
    return filtered


print("=" * 70)
print("  CALENDAR EFFECTS + STRATEGY ENHANCEMENT SCAN")
print("  EURUSD D1 | Cost: %.1f bps/RT" % COST)
print("=" * 70)

df = pd.read_csv(DATA)
O = df["Open"].values; H = df["High"].values; L = df["Low"].values; C = df["Close"].values
dates = df["Date"].values
n = len(C)
sp = int(n * TRAIN)

all_results = []

# ================================================================
# 1. Pure Calendar Effects
# ================================================================
print("\n--- Pure Calendar Effects ---")

for name, rule, args in [
    ("Monday", "dow", [0]),
    ("Friday", "dow", [4]),
    ("MidWeek(Tue-Thu)", "dow", [1, 2, 3]),
    ("January", "month", [1]),
    ("Dec-Feb", "month", [12, 1, 2]),
    ("TurnOfMonth", "tom", None),
    ("MidMonth(10-20)", "mid_month", None),
]:
    for arg in (args or [None]):
        # Build always-long signal (benchmark)
        sigs = np.ones(n, dtype=int)  # always long
        filtered = calendar_filter(dates, sigs, rule.split("(")[0].lower().replace(" ", "_"), arg)
        trades = eval_strategy(O, C, filtered)
        s, ann = sharpe_from_returns(trades)
        wr = sum(1 for x in trades if x > 0) / max(1, len(trades)) * 100
        label = name if arg is None else f"{name}({arg})"
        all_results.append({"cat": "Calendar", "name": label,
                            "oos_sharpe": s, "oos_trades": len(trades),
                            "oos_wr": wr, "ann_ret": ann})
        if len(trades) >= 5:
            print(f"  {label:25s}: Sharpe={s:+7.2f} Trades={len(trades):4d} WR={wr:5.1f}% AnnRet={ann:+6.1f}%")

# ================================================================
# 2. Donchian + Calendar Filters (enhancement)
# ================================================================
print("\n--- Donchian(25) + Calendar Enhancement ---")

base_sigs = donchian_signals(H, L, C, 25)

for name, rule, args in [
    ("D25+Monday", "dow", [0]),
    ("D25+Friday", "dow", [4]),
    ("D25+TurnOfMonth", "tom", None),
    ("D25+NoMidMonth", "not_mid", None),
    ("D25+Jan", "month", [1]),
    ("D25+DecFeb", "month", [12, 1, 2]),
]:
    for arg in (args or [None]):
        filtered = calendar_filter(dates, base_sigs.copy(), rule.split("(")[0].lower(), arg)
        trades = eval_strategy(O, C, filtered)
        s, ann = sharpe_from_returns(trades)
        wr = sum(1 for x in trades if x > 0) / max(1, len(trades)) * 100
        label = name if arg is None else f"{name}({arg})"
        all_results.append({"cat": "Enhance", "name": label,
                            "oos_sharpe": s, "oos_trades": len(trades),
                            "oos_wr": wr, "ann_ret": ann})
        if len(trades) >= 5:
            print(f"  {label:25s}: Sharpe={s:+7.2f} Trades={len(trades):4d} WR={wr:5.1f}% AnnRet={ann:+6.1f}%")

# ================================================================
# 3. Volatility Filter + Donchian
# ================================================================
print("\n--- Donchian(25) + Volatility Filter ---")

for vr in [0.5, 0.75, 1.0, 1.25, 1.5]:
    filtered = vol_filter(base_sigs.copy(), C, vr)
    trades = eval_strategy(O, C, filtered)
    s, ann = sharpe_from_returns(trades)
    wr = sum(1 for x in trades if x > 0) / max(1, len(trades)) * 100
    label = f"D25+Vol>{vr:.2f}"
    all_results.append({"cat": "VolFilter", "name": label,
                        "oos_sharpe": s, "oos_trades": len(trades),
                        "oos_wr": wr, "ann_ret": ann})
    if len(trades) >= 5:
        print(f"  {label:25s}: Sharpe={s:+7.2f} Trades={len(trades):4d} WR={wr:5.1f}% AnnRet={ann:+6.1f}%")

# ================================================================
# 4. D25 with ATR Trailing Stop
# ================================================================
print("\n--- Donchian(25) + ATR Trailing Stop ---")

for trail in [1.0, 2.0, 3.0, 5.0]:
    # Implement trailing stop: exit when price moves `trail * ATR` against position
    n = len(C)
    atr = np.zeros(n)
    for i in range(14, n):
        tr = max(H[i] - L[i], abs(H[i] - C[i-1]), abs(L[i] - C[i-1]))
        atr[i] = (atr[i-1]*13 + tr)/14 if atr[i-1] else tr

    pos, entry_px = 0, 0.0
    peak_price = 0.0
    trades = []
    for i in range(WARMUP, n):
        bar = "OOS" if i >= sp else "IS"
        sig = base_sigs[i]
        atr_val = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else C[i] * 0.005

        if pos == 0 and sig != 0:
            ei = i + 1 if i + 1 < n else i
            entry_px = O[ei] if i + 1 < n else C[i]
            pos = sig
            peak_price = entry_px
        elif pos != 0:
            # Update trailing peak
            if pos == 1 and C[i] > peak_price:
                peak_price = C[i]
            elif pos == -1 and C[i] < peak_price:
                peak_price = C[i]

            # Check trailing stop
            stop_hit = False
            if pos == 1 and C[i] < peak_price - trail * atr_val:
                stop_hit = True
            elif pos == -1 and C[i] > peak_price + trail * atr_val:
                stop_hit = True

            if stop_hit or sig != pos:
                ei = i + 1 if i + 1 < n else i
                exit_px = O[ei] if i + 1 < n else C[i]
                r = (exit_px - entry_px) / entry_px if pos == 1 else (entry_px - exit_px) / entry_px
                if bar == "OOS":
                    trades.append(r - COST / 10000.0)
                pos = 0
                if sig != 0 and not stop_hit:
                    entry_px = exit_px
                    pos = sig
                    peak_price = entry_px

    s, ann = sharpe_from_returns(trades)
    wr = sum(1 for x in trades if x > 0) / max(1, len(trades)) * 100
    label = f"D25+Trail{trail:.0f}ATR"
    all_results.append({"cat": "TrailStop", "name": label,
                        "oos_sharpe": s, "oos_trades": len(trades),
                        "oos_wr": wr, "ann_ret": ann})
    print(f"  {label:25s}: Sharpe={s:+7.2f} Trades={len(trades):4d} WR={wr:5.1f}% AnnRet={ann:+6.1f}%")

# ================================================================
# Ranking
# ================================================================
print(f"\n{'='*70}")
print("  RANKED — Calendar + Enhancement Strategies")
print(f"{'='*70}")

valid = [r for r in all_results if r["oos_trades"] >= 5]
valid.sort(key=lambda x: x["oos_sharpe"], reverse=True)

print(f"\n{'#':<3} {'Name':<28} {'Cat':<12} {'Sharpe':<10} {'Trades':<8} {'WR%':<7} {'AnnRet%':<9}")
print("-" * 80)
for i, r in enumerate(valid[:20], 1):
    print(f"{i:<3} {r['name']:<28} {r['cat']:<12} {r['oos_sharpe']:+9.2f}  "
          f"{r['oos_trades']:<8d} {r['oos_wr']:<6.1f}% {r['ann_ret']:+8.1f}%")

with open(BASE / "reports" / "calendar_enhance_scan.json", "w") as f:
    json.dump({"date": str(pd.Timestamp.now()), "results": valid}, f, indent=2)

print(f"\nSaved: reports/calendar_enhance_scan.json")
print("=" * 70)
