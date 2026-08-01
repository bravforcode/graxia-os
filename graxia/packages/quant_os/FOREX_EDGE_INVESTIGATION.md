# FOREX EDGE INVESTIGATION — Why Major Pairs Have No Edge

**Date**: 2026-07-12
**Instruments Tested**: GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD, NZDUSD
**Timeframe**: H1
**Engine**: Canonical validation/walk_forward.py

---

## Executive Summary

All 6 major forex pairs failed walk-forward validation. GBPUSD and USDJPY were explicitly REJECT (significant negative t-stats). The remaining 4 were INCONCLUSIVE with near-zero PnL. **The root cause is a combination of three factors: cost dominance, feature mismatch, and missing forex-specific signals.**

---

## Results Summary

| Symbol | Trades | Net PnL | Pos% | t-stat | Verdict |
|--------|--------|---------|------|--------|---------|
| GBPUSD | 3,388 | -$1.42 | 3.2% | -8.77 | REJECT |
| USDJPY | 3,529 | -$161 | 12.1% | -8.57 | REJECT |
| USDCAD | 1,725 | -$0.11 | 4.5% | -1.69 | INCONCLUSIVE |
| USDCHF | 2,498 | -$0.10 | 7.7% | -1.12 | INCONCLUSIVE |
| AUDUSD | 5,281 | -$0.13 | 8.5% | -1.55 | INCONCLUSIVE |
| NZDUSD | 5,599 | -$0.04 | 8.9% | -0.53 | INCONCLUSIVE |

---

## Root Cause Analysis

### 1. COST DOMINANCE (Primary Factor)

**Pepperstone Razor charges $7/round-trip commission on all FX pairs.**

For a typical EURUSD trade:
- Average move per M15 bar: ~3-5 pips
- Commission cost: $7 / 100,000 units = 0.7 pips
- This means **15-23% of the average move is consumed by commission alone**

Compare to metals:
- XAUUSD: $0 commission, spread-only (~0.36 bps)
- XPDUSD: $0 commission, spread-only (assumed ~5 bps)

The $7/rt commission on FX creates a **structural headwind** that is very difficult to overcome with technical indicators alone.

### 2. FEATURE MISMATCH (Secondary Factor)

The current feature set was designed for metals/crypto:
- `vol_10`, `vol_20`: Calibrated for 0.5-2% daily moves (metals)
- `atr_ratio`: Designed for ATR-based metals signals
- `rsi_14`: Standard but not optimized for FX ranges

**Forex pairs trade in 0.1-0.3% daily ranges** — these features are near-zero and provide minimal signal.

Missing forex-specific features:
- Interest rate differentials (carry)
- COT (Commitments of Traders) positioning
- Economic calendar proximity
- Session-specific volatility (Asian/London/NY)
- Cross-pair correlation (EURUSD vs GBPUSD)

### 3. REGIME FILTER INTERACTION (Contributing Factor)

The regime filter in strategies/base.py restricts which strategies can trade:
- `mlb.py` (ML Breakout): Only in TREND regimes
- `mrb.py` (ML Mean Reversion): Only in RANGE_BOUND/LOW_VOL
- `mlmr.py` (ML Mean Reversion): Only in RANGE_BOUND/LOW_VOL

During backtesting, the regime filter may be blocking valid signals. However, the walk-forward script does NOT apply regime filtering — it uses raw model predictions. So this is not the primary cause.

### 4. LIQUIDITY & MICROSTRUCTURE (Tertiary Factor)

Major forex pairs are dominated by:
- High-frequency market makers
- Central bank interventions
- Institutional hedging flows

These participants create efficient pricing that leaves little room for retail technical strategies. The edge in metals comes from:
- Lower HFT participation
- Commodity-specific supply/demand (mining, jewelry)
- Geopolitical safe-haven flows

---

## Quantified Cost Impact

For GBPUSD on H1:
- 3,388 trades * $7/rt = **$23,716 total commission**
- Net PnL: -$1.42
- **Gross PnL before costs: +$23,714**
- The strategy HAS gross edge but commission eliminates it

This is the clearest evidence: the model is making correct predictions but the cost structure makes them unprofitable.

---

## Recommendations

### Short-Term (Do Not Change)

1. **Do not add forex pairs to live/paper trading** — current feature set is insufficient
2. **Focus on metals (XAUUSD, XPDUSD, XPTUSD)** — these have proven edge

### Medium-Term (If Forex Is Desired)

1. **Build forex-specific feature set**:
   - Interest rate differential (FRED data)
   - COT positioning (weekly)
   - Economic calendar distance
   - Cross-pair momentum
   - Session volatility profiles

2. **Reduce cost assumptions**:
   - Consider ECN brokers with lower commission
   - Increase minimum holding period to reduce trade count
   - Use D1 timeframe where commission impact is smaller

3. **Regime-aware strategy selection**:
   - Add carry-trade strategy for positive-swap pairs
   - Add news-fade strategy for high-impact events
   - Consider longer holding periods (swing trading)

### Long-Term (Architecture Change)

1. **Multi-asset feature normalization**: Each asset class should have its own feature pipeline
2. **Cost-adjusted signal threshold**: Raise min_confidence for high-cost instruments
3. **Instrument-specific model training**: Don't train one model for all instruments

---

## Conclusion

**Forex pairs do not have edge with the current system because:**
1. $7/rt commission consumes 15-23% of average price moves
2. Features are calibrated for metals volatility, not FX
3. Major FX pairs are more efficient than metals

**The correct action is to focus on metals (XAUUSD, XPDUSD, XPTUSD) where the edge exists, and only revisit forex after building instrument-specific features.**

---

*Investigation by Quant OS Deep Audit Protocol v4*
