"""
Pairs Trading Scan — EURUSD/GBPUSD D1
Tests mean reversion on the spread between EURUSD and GBPUSD.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
COST = 3.4
TRAIN = 0.80
WARMUP = 50


def load_pair(fname):
    df = pd.read_csv(BASE / "data" / fname)
    cols = {c.lower(): c for c in df.columns}
    return df[cols["close"]].values.astype(float)


def sharpe(trades):
    if len(trades) < 5: return 0, 0
    avg = np.mean(trades)
    std = np.std(trades, ddof=1)
    return float(avg / (std + 1e-10) * np.sqrt(252)), len(trades)


def run_pairs():
    print("=" * 70)
    print("  PAIRS TRADING SCAN — EURUSD/GBPUSD D1")
    print("=" * 70)

    eu = load_pair("EURUSD_D1_clean.csv")
    gu = load_pair("GBPUSD_D1.csv")

    # Align lengths
    n = min(len(eu), len(gu))
    eu, gu = eu[-n:], gu[-n:]
    sp = int(n * TRAIN)
    print(f"  Bars: {n} | IS: {sp} | OOS: {n-sp}")
    print(f"  EURUSD range: {eu[-1]:.4f} - {eu[0]:.4f}")
    print(f"  GBPUSD range: {gu[-1]:.4f} - {gu[0]:.4f}")

    # Compute log prices and spread
    log_eu = np.log(eu)
    log_gu = np.log(gu)

    # Estimate hedge ratio (beta) on first half of train data
    train_eu = log_eu[:sp//2]
    train_gu = log_gu[:sp//2]
    # OLS: log_eu = alpha + beta * log_gu
    cov = np.cov(train_eu, train_gu)
    beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 1.0
    spread = log_eu - beta * log_gu
    print(f"  Hedge ratio (beta): {beta:.4f}")
    print(f"  Spread mean: {np.mean(spread):.4f}, std: {np.std(spread):.4f}")

    # Rolling z-score
    results = []
    for window in [20, 50, 100, 200]:
        for entry_z in [1.5, 2.0, 2.5]:
            trades_is, trades_oos = [], []
            for i in range(max(window, WARMUP), n):
                bar = "OOS" if i >= sp else "IS"
                w = spread[max(0, i - window):i]
                mu = np.mean(w)
                sigma = np.std(w, ddof=1) if len(w) > 1 else 0
                if sigma == 0:
                    continue
                z = (spread[i] - mu) / sigma

                # Simple entry/exit on next bar
                if abs(z) > entry_z:
                    # Simulate trade: entry next bar, exit when cross 0
                    entry_i = i + 1 if i + 1 < n else i
                    entry_z_val = z

                    # Find exit: when z-score crosses 0 or after max_hold bars
                    max_hold = min(100, n - entry_i - 1)
                    exit_i = entry_i
                    for j in range(entry_i + 1, min(entry_i + max_hold, n)):
                        w2 = spread[max(0, j - window):j]
                        mu2 = np.mean(w2)
                        sigma2 = np.std(w2, ddof=1) if len(w2) > 1 else 0
                        if sigma2 == 0:
                            exit_i = j
                            break
                        z2 = (spread[j] - mu2) / sigma2
                        if np.sign(z2) != np.sign(entry_z_val):
                            exit_i = j
                            break
                    else:
                        exit_i = min(entry_i + max_hold, n - 1)

                    # Trade return
                    sp_entry = spread[entry_i]
                    sp_exit = spread[exit_i]
                    if z > 0:  # spread high → short spread (sell EUR, buy GBP)
                        ret = (sp_entry - sp_exit) - (COST / 10000.0) * 2  # 2 legs
                    else:  # spread low → long spread (buy EUR, sell GBP)
                        ret = (sp_exit - sp_entry) - (COST / 10000.0) * 2

                    (trades_is if bar == "IS" else trades_oos).append(ret)
                    i = exit_i  # skip ahead

            is_s, is_n = sharpe(trades_is)
            oos_s, oos_n = sharpe(trades_oos)

            if oos_n >= 5:
                results.append({
                    "window": window, "entry_z": entry_z,
                    "is_sharpe": is_s, "oos_sharpe": oos_s,
                    "oos_trades": oos_n, "is_trades": is_n,
                    "beta": round(float(beta), 4),
                })
                print(f"    win={window:3d},z={entry_z:.1f}: IS={is_s:7.2f} OOS={oos_s:7.2f} "
                      f"Trades={oos_n:3d}")

    # Rank
    results.sort(key=lambda x: x["oos_sharpe"], reverse=True)
    print(f"\n  Best: win={results[0]['window']}, z={results[0]['entry_z']} "
          f"OOS Sharpe={results[0]['oos_sharpe']:.2f} Trades={results[0]['oos_trades']}")

    with open(BASE / "reports" / "pairs_trading_scan.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved: reports/pairs_trading_scan.json")
    print("=" * 70)


if __name__ == "__main__":
    run_pairs()
