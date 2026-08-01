"""
SPARC Phase 2: Quick Edge Verification
Run Momentum12M vs RandomSignal on XAUUSD H1 to check if edge exists.
"""
import sys
sys.path.insert(0, '.')

from quant_os.tests.test_label_shuffling import (
    RandomSignalStrategy,
    _load_xauusd_h1,
    _load_xauusd_d1,
    _compute_sharpe_from_engine,
    run_label_shuffle_test,
)
from quant_os.strategies.momentum_12m import Momentum12M
from quant_os.backtest.engine import BacktestConfig
from decimal import Decimal
import time

print("=" * 60)
print("SPARC PHASE 2: EDGE VERIFICATION")
print("=" * 60)

# --- Config ---
H1_BARS = 2000  # ~83 days of H1 data

# --- Load H1 data ---
print("\n--- Loading XAUUSD H1 data ---")
h1_data = _load_xauusd_h1()
for k in h1_data:
    h1_data[k] = h1_data[k][-H1_BARS:]
print(f"Loaded: {len(h1_data['close'])} bars")

config = BacktestConfig(
    initial_capital=Decimal("10000"),
    slippage_pips=0.5,
    spread_pips=2.0,
    commission_per_lot=Decimal("3.5"),
    risk_per_trade_bps=100,
    strict_mtf=False,
    max_positions=5,
)

# --- Test 1: Random Strategy Sharpe ---
print("\n--- Test 1: Random Strategy (null distribution) ---")
start = time.time()
random_strat = RandomSignalStrategy(seed=42)
random_sharpe = _compute_sharpe_from_engine(random_strat, h1_data, "XAUUSD", config)
elapsed = time.time() - start
print(f"Random Sharpe: {random_sharpe:.4f} ({elapsed:.1f}s)")

# --- Test 2: Momentum12M Sharpe ---
print("\n--- Test 2: Momentum12M (real strategy) ---")
start = time.time()
momentum_strat = Momentum12M(lookback=252, atr_period=14, atr_sl_mult=2.0, atr_tp_mult=3.0)
momentum_sharpe = _compute_sharpe_from_engine(momentum_strat, h1_data, "XAUUSD", config)
elapsed = time.time() - start
print(f"Momentum12M Sharpe: {momentum_sharpe:.4f} ({elapsed:.1f}s)")

# --- Test 3: Run label shuffle test (50 permutations) ---
print("\n--- Test 3: Label Shuffle Test (50 permutations) ---")
print("This will take a while...")
start = time.time()
result = run_label_shuffle_test(
    strategy=momentum_strat,
    data=h1_data,
    symbol="XAUUSD",
    n_permutations=50,
    config=config,
    seed=42,
)
elapsed = time.time() - start

print(f"\n{'='*60}")
print(f"RESULTS (took {elapsed:.1f}s)")
print(f"{'='*60}")
print(f"  Real Sharpe:     {result['real_sharpe']:.4f}")
print(f"  Null mean:       {result['null_mean']:.4f}")
print(f"  Null std:        {result['null_std']:.4f}")
print(f"  Null 95th pct:   {result['null_95th_percentile']:.4f}")
print(f"  p-value:         {result['p_value']:.4f}")
print(f"  Survives:        {result['survives']}")
print()

if result["survives"]:
    print("  VERDICT: Edge may be real — survives null hypothesis test")
    print("  NEXT: Fix cost bugs, multi-asset pooling, then paper trade")
else:
    print("  VERDICT: NO EDGE — real Sharpe falls inside null distribution")
    print("  NEXT: Consider STOP or pivot to different instrument/approach")
