"""Run backtest on multiple symbols and print results."""
import sys
import os
import MetaTrader5 as mt5

sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.backtest.engine import run_backtest


def main():
    mt5.initialize()

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
    results = []

    print("=" * 70)
    print("QUANT OS BACKTEST — 5000 M15 bars (~52 days)")
    print("=" * 70)

    for sym in symbols:
        r = run_backtest(symbol=sym, bars=5000, risk_pct=0.5, initial_capital=50000)
        if "error" not in r:
            results.append(r)
            print(f"{sym}: Return={r['return_pct']:+.1f}% Sharpe={r['sharpe']:.2f} "
                  f"WinRate={r['win_rate_pct']:.0f}% MaxDD={r['max_drawdown_pct']:.1f}% "
                  f"Trades={r['total_trades']} PnL=${r['total_pnl']:+,.0f}")

    if results:
        print("-" * 70)
        avg_return = sum(r["return_pct"] for r in results) / len(results)
        avg_sharpe = sum(r["sharpe"] for r in results) / len(results)
        avg_winrate = sum(r["win_rate_pct"] for r in results) / len(results)
        avg_dd = sum(r["max_drawdown_pct"] for r in results) / len(results)
        avg_ror = sum(r.get("risk_of_ruin", 0) for r in results) / len(results)
        avg_kelly = sum(r.get("kelly_fraction", 0) for r in results) / len(results)
        total_pnl = sum(r["total_pnl"] for r in results)
        print(f"AVG: Return={avg_return:+.1f}% Sharpe={avg_sharpe:.2f} "
              f"WinRate={avg_winrate:.0f}% MaxDD={avg_dd:.1f}%")
        print(f"Risk: Ruin={avg_ror:.1f}% Kelly={avg_kelly:.1f}% TotalPnL=${total_pnl:+,.0f}")

    mt5.shutdown()


if __name__ == "__main__":
    main()
