"""
Quick Start Script - Download data, run backtest, train ML model

Usage:
    cd "graxia os" directory
    python graxia/packages/quant_os/run_backtest.py
"""

import sys
import os
import json
from datetime import datetime, timezone

# Add graxia os root to path (current working directory when run from graxia os)
sys.path.insert(0, os.getcwd())

# Use absolute imports
from graxia.packages.quant_os.backtest.data_loader import download_and_save_yahoo, load_yahoo_csv, generate_sample_data
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.backtest.metrics import calculate_metrics
from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum
from graxia.packages.quant_os.strategies.mrb import MeanReversionBollinger
from graxia.packages.quant_os.strategies.mlb import MLBreakout
from graxia.packages.quant_os.strategies.ensemble import EnsembleStrategy


def step1_download_data():
    """Download EURUSD data from Yahoo Finance"""
    print("=" * 60)
    print("STEP 1: Downloading EURUSD data...")
    print("=" * 60)
    
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    csv_path = os.path.join(data_dir, "EURUSD=X.csv")
    
    if os.path.exists(csv_path):
        print(f"Data file exists: {csv_path}")
        print("Loading existing data...")
        data, timestamps = load_yahoo_csv("EURUSD=X", data_dir)
    else:
        print("Downloading from Yahoo Finance...")
        try:
            download_and_save_yahoo("EURUSD=X", "2020-01-01", "2024-12-31", data_dir)
            data, timestamps = load_yahoo_csv("EURUSD=X", data_dir)
        except Exception as e:
            # FAIL-LOUD: ไม่ fallback เงียบๆ — หยุดแล้วแจ้งเตือน
            raise RuntimeError(
                f"\n{'='*60}\n"
                f"DATA FETCH FAILED — CANNOT CONTINUE\n"
                f"{'='*60}\n"
                f"Yahoo Finance download failed: {e}\n\n"
                f"WHY THIS MATTERS:\n"
                f"  Backtesting on synthetic data produces meaningless results.\n"
                f"  The system refuses to proceed with fake data.\n\n"
                f"FIX:\n"
                f"  1. Check internet connection\n"
                f"  2. Check if Yahoo Finance is accessible\n"
                f"  3. Manually download EURUSD data and place in data/ folder\n"
                f"  4. Or use MT5 data loader: load_mt5_data('EURUSD', 'M15')\n"
                f"{'='*60}"
            )
    
    print(f"Loaded {len(data['close'])} bars")
    print(f"Date range: {timestamps[0]} to {timestamps[-1]}")
    print(f"Price range: {min(data['close']):.5f} - {max(data['close']):.5f}")
    
    return data, timestamps


def step2_run_backtest(data, timestamps):
    """Run backtest with MTM strategy"""
    print("\n" + "=" * 60)
    print("STEP 2: Running Backtest...")
    print("=" * 60)
    
    config = BacktestConfig(
        initial_capital=10000.0,
        slippage_pips=0.5,
        commission_per_lot=3.5,
        risk_per_trade_pct=1.0,
        max_positions=3,
    )
    
    # Test MTM strategy
    print("\n--- Multi-Timeframe Momentum (MTM) ---")
    mtm = MultiTimeframeMomentum()
    engine = BacktestEngine(config)
    engine.set_strategy(mtm)
    engine.load_data(data, timestamps)
    results = engine.run()
    
    m = results["metrics"]
    print(f"Total Trades: {m.total_trades}")
    print(f"Win Rate: {m.win_rate:.1%}")
    print(f"Profit Factor: {m.profit_factor:.2f}")
    print(f"Sharpe Ratio: {m.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {m.max_drawdown_pct:.2f}%")
    print(f"Total P&L: ${m.total_pnl:+,.2f}")
    print(f"Expectancy: ${m.expectancy:+,.2f}")
    
    return results


def step3_run_all_strategies(data, timestamps):
    """Run backtest with all strategies"""
    print("\n" + "=" * 60)
    print("STEP 3: Comparing All Strategies...")
    print("=" * 60)
    
    config = BacktestConfig(
        initial_capital=10000.0,
        slippage_pips=0.5,
        commission_per_lot=3.5,
        risk_per_trade_pct=1.0,
        max_positions=3,
    )
    
    strategies = [
        ("MTM", MultiTimeframeMomentum),
        ("MRB", MeanReversionBollinger),
        ("MLB", MLBreakout),
    ]
    
    all_results = {}
    
    for name, strategy_class in strategies:
        print(f"\n--- {name} ---")
        try:
            strategy = strategy_class()
            engine = BacktestEngine(config)
            engine.set_strategy(strategy)
            engine.load_data(data, timestamps)
            results = engine.run()
            m = results["metrics"]
            print(f"  Trades: {m.total_trades}, Win Rate: {m.win_rate:.1%}, "
                  f"PF: {m.profit_factor:.2f}, Sharpe: {m.sharpe_ratio:.2f}, "
                  f"Max DD: {m.max_drawdown_pct:.2f}%, P&L: ${m.total_pnl:+,.2f}")
            all_results[name] = results
        except Exception as e:
            print(f"  Error: {e}")
    
    return all_results


def main():
    """Run full backtest pipeline"""
    print("Quant OS - Backtest Pipeline")
    print("=" * 60)
    
    # Step 1: Download data
    data, timestamps = step1_download_data()
    
    # Step 2: Run MTM backtest
    mtm_results = step2_run_backtest(data, timestamps)
    
    # Step 3: Compare all strategies
    all_results = step3_run_all_strategies(data, timestamps)
    
    # Save results
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, "backtest_results.json")
    
    # Convert metrics to dict for JSON serialization
    def metrics_to_dict(m):
        return {
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "win_rate": m.win_rate,
            "total_pnl": m.total_pnl,
            "total_return_pct": m.total_return_pct,
            "avg_win": m.avg_win,
            "avg_loss": m.avg_loss,
            "avg_rr": m.avg_rr,
            "expectancy": m.expectancy,
            "profit_factor": m.profit_factor,
            "max_drawdown": m.max_drawdown,
            "max_drawdown_pct": m.max_drawdown_pct,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "calmar_ratio": m.calmar_ratio,
            "cagr": m.cagr,
        }
    
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_bars": len(data["close"]),
            "strategies": {
                name: {
                    "metrics": metrics_to_dict(r["metrics"]),
                    "trade_count": len(r["trades"]),
                }
                for name, r in all_results.items()
            }
        }, f, indent=2, default=str)
    
    print(f"\n{'=' * 60}")
    print(f"Results saved to: {output_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
