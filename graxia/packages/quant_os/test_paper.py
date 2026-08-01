"""
Quick paper trading test — fetch MT5 data, run strategies, report signals.
"""

import json
import os
import sys
from pathlib import Path

# Setup paths — graxia os root is 3 levels up from quant_os
BASE = Path(__file__).resolve().parent
GRAXIA_OS = BASE.parent.parent.parent  # quant_os -> packages -> graxia -> graxia os
sys.path.insert(0, str(GRAXIA_OS))

from dotenv import load_dotenv

load_dotenv(BASE / ".env")

# Import after path setup
import MetaTrader5 as mt5

from graxia.packages.quant_os.strategies.mlb import MLBreakout
from graxia.packages.quant_os.strategies.mlmr import MLMeanReversion

SYMBOLS = ["XAUUSD", "EURUSD", "US30", "NAS100", "BTCUSD"]


def connect_mt5():
    """Connect to MT5."""
    login = int(os.getenv("MT5_LOGIN"))
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    path = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

    ok = mt5.initialize(path=path, login=login, password=password, server=server, timeout=60000)
    if not ok:
        print(f"MT5 connection failed: {mt5.last_error()}")
        sys.exit(1)

    acct = mt5.account_info()
    print(f"Connected: {acct.login}@{acct.server}  Balance=${acct.balance:,.2f}")
    return acct


def fetch_data(symbol: str, n_bars: int = 300) -> dict | None:
    """Fetch M15 OHLCV data."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None

    return {
        "time": [r[0] for r in rates],
        "open": [r[1] for r in rates],
        "high": [r[2] for r in rates],
        "low": [r[3] for r in rates],
        "close": [r[4] for r in rates],
        "volume": [r[5] for r in rates],
    }


def main():
    # Connect
    acct = connect_mt5()
    print()

    # Fetch data
    print("=== Market Data (M15) ===")
    data_cache = {}
    for sym in SYMBOLS:
        ohlcv = fetch_data(sym)
        if ohlcv:
            data_cache[sym] = ohlcv
            last = ohlcv["close"][-1]
            print(f"  {sym}: {len(ohlcv['close'])} bars, close={last:.5f}")
        else:
            print(f"  {sym}: NO DATA")
    print()

    # Init strategies
    strategies = {
        "MLB": MLBreakout(),
        "MLMR": MLMeanReversion(),
    }

    # Run strategies
    print("=== Strategy Signals ===")
    all_signals = []

    for sym in SYMBOLS:
        if sym not in data_cache:
            continue

        ohlcv = data_cache[sym]

        for name, strat in strategies.items():
            try:
                sig = strat.generate_signal(symbol=sym, ohlcv_data=ohlcv)
                if sig:
                    entry = float(sig.entry_price) if sig.entry_price else 0
                    sl = float(sig.stop_loss) if sig.stop_loss else 0
                    tp = float(sig.take_profit) if sig.take_profit else 0
                    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0

                    signal_info = {
                        "strategy": name,
                        "symbol": sym,
                        "type": sig.signal_type.value,
                        "confidence": round(sig.confidence, 3),
                        "entry": round(entry, 5),
                        "sl": round(sl, 5),
                        "tp": round(tp, 5),
                        "rr": round(rr, 2),
                        "notes": sig.notes,
                    }
                    all_signals.append(signal_info)

                    print(
                        f"  [{name}] {sym}: {sig.signal_type.value}  conf={sig.confidence:.3f}  entry={entry:.5f}  SL={sl:.5f}  TP={tp:.5f}  R:R={rr:.2f}"
                    )
                else:
                    print(f"  [{name}] {sym}: no signal")
            except Exception as e:
                print(f"  [{name}] {sym}: ERROR - {e}")

    # Summary
    print()
    print("=== Summary ===")
    print(f"Total signals: {len(all_signals)}")

    if all_signals:
        buys = [s for s in all_signals if s["type"] == "BUY"]
        sells = [s for s in all_signals if s["type"] == "SELL"]
        print(f"  BUY signals:  {len(buys)}")
        print(f"  SELL signals: {len(sells)}")

        # Best signal by confidence
        best = max(all_signals, key=lambda s: s["confidence"])
        print(f"  Best: {best['strategy']} {best['symbol']} {best['type']} (conf={best['confidence']})")

        # Save
        report_path = BASE / "reports" / "latest_signals.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(all_signals, f, indent=2)
        print(f"\nSaved to {report_path}")
    else:
        print("  No signals generated — market may be quiet or no setups triggered.")

    mt5.shutdown()
    print("\nPaper trading test COMPLETE")


if __name__ == "__main__":
    main()
