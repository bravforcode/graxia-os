## Phase F — Backtest with Real Costs (UNVERIFIED — 26 Jun 2026)

> **⚠️ UNVERIFIED:** This document contains numbers from a previous version of the code.
> The cost model has been fixed to use per-trade prices (not flat $2350).
> The Sharpe calculation has been fixed with minimum sample size.
> Deflated Sharpe has been added for multiple-testing correction.
> **Rerun backtest_cost.py to get verified numbers.**

### Result: ❌ 1min XAUUSD does NOT survive real costs
- **Bug fixed**: `simulate_fills.py` had ms/ns unit bug (added 50,000,000ms=13.9hr instead of 50ms). Fixed P90 slippage: **6367pts→39pts** ($63.67→$0.39).
- **Pipeline works end-to-end**: features V2 → XGBoost → regime filter → real-cost backtest
- **Edge is REAL**: 58.2% accuracy OOS at conf≥0.75 (67 trades, 6.7% bars)
- **Gross P&L**: +$14.31 on 67 trades (@ $0.21/trade avg gross)
- **Real costs**: $0.17 spread + $0.39 slippage P90 = **$0.56/trade**
- **Net P&L**: **-$23.21** (costs of $37.52 eat all edge)
- **Why it fails**: High-confidence predictions occur on LOW-VOLATILITY bars (avg move=$0.21 vs full-dataset avg $0.67). Confident model + regime filter selects quiet bars where edge is too small vs fixed costs.
- **5min/15min**: Insufficient data (2.3 days only). 5min: 453 train samples → 100% train acc, 46% OOS (overfit). 15min: 142 samples → useless. Regime filter also breaks at higher TFs (conf_score=0). Need 2+ weeks of data.
- **Triple-barrier 1min**: Model can't predict tb_label (50.15% OOS = random) → no edge.
- **Cost/move ratio**: 83% (cost per trade / avg move). Fundamental breakeven requires 350pts avg move ($3.50/trade) at 58% accuracy.

### What we learned
1. **Pipeline is solid**: Feature engineering → XGBoost → regime filter → fill simulator → real-cost backtest all connected and working
2. **Regime filter + confidence selects low-vol bars**: Confident predictions cluster on quiet markets → smaller returns → cannot cover costs
3. **Still profitable with spread-only**: conf≥0.75 → net +$5.98 (from regime_filter.py evaluation with spread_cost=$0.17 only, no slippage)
4. **The edge exists but is thin**: 58% acc vs 50% baseline, confirmed Bonferroni+WF in feature diagnostic

### Next Steps
1. **Collect more data**: Run mega_collect for 2+ weeks → enables 5min/15min training with larger moves
2. **EURUSD/GBPUSD**: Tighter spreads (~0.5pts vs 17pts XAUUSD) → much better cost/move ratio
3. **Limit orders**: Save entry half-spread → reduce per-trade cost by ~30%
4. **Wider triple-barrier barriers**: Increase k multiplier for larger per-trade returns
5. **Background jobs still running**: 500 orders, spread heatmap 24h — results pending
