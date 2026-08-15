# Regime-Adaptive Ensemble — System Design (Honest Draft)

> This is a **design document**, not a validation report. No strategy in this
> document has passed pooled DK-test or label-shuffle. All "✅" marks below
> refer to **code exists**, not "edge proven".

---

## Architecture (as-designed, not as-validated)

The ensemble votes 3 strategies with regime-conditional weights:

| Strategy | Role | Weight | Code status | Edge status |
|----------|------|--------|-------------|-------------|
| Multi-Timeframe Momentum (MTM) | Trend following | 0.40 | `strategies/mtm.py` exists | **0 signals on D1 test** — needs MTF indicators not wired into BacktestEngine |
| Mean Reversion Bollinger (MRB) | Range-bound contrarian | 0.25 | `strategies/mrb.py` exists | **0 signals on D1 test** — needs BB/ADX/Stoch indicators not wired |
| ML Breakout (MLB) | Pattern-based | 0.35 | `strategies/mlb.py` exists | Needs trained XGBoost model — **never trained or evaluated** |

**Critical gap:** 65% of ensemble weight (MTM 0.40 + MRB 0.25) = strategies that produce **zero signals** in the current BacktestEngine because their required indicators (EMA 200, ADX, Stochastic, multi-timeframe data) are not computed by the engine's `_calculate_indicators()` path.

### What actually works in BacktestEngine

Strategies that only need OHLCV + ATR compute their own indicators inline:
- RSIMeanReversion ✅ (computes RSI internally)
- DonchianBreakout ✅ (computes Donchian channels internally)
- HybridMomMR ✅ (computes momentum internally)
- Momentum12M ✅ (computes returns internally)
- BollingerSqueeze ✅ (computes BB internally)

Strategies that need external indicators or multi-timeframe data:
- MTM ❌ (needs `ema_200`, `h4_ema_200`, `h1_ema_200`, `rsi_14`, `volume_sma_20`)
- MRB ❌ (needs `bb_upper`, `bb_middle`, `bb_lower`, `adx`, `stoch_k`, `stoch_d`, `rsi`)
- MLB ❌ (needs trained model)

### Regime switching logic

Designed to switch between strategies by regime:
- `TREND_*` → weight MTM + Donchian
- `RANGE_*` → weight MRB + RSI
- `HIGH_VOL` → weight Donchian + VolumeBreakout

**Status:** Regime detection code exists (`regime/regime_detector.py`) but the ensemble strategy never calls it — the regime switching is architectural, not wired.

---

## Per-Strategy Edge Status (from EDGE_SEARCH_FINAL_20260718.md)

### Strategies tested on D1 pooled (DK-test, 7 assets, realistic costs)

All 17 tested strategies: **REJECT** (dk_t < 0)

| Strategy | DK-t | Trades | Verdict |
|----------|------|--------|---------|
| RSI_20_80 | -0.22 | 214 | REJECT |
| Momentum12M_252 | -0.39 | 3548 | REJECT |
| HybridMomMR_60 | -0.42 | 3706 | REJECT |
| Donchian_10 | -0.61 | 2293 | REJECT |
| Donchian_20 | -0.75 | 1771 | REJECT |
| DonchianADX_10_25 | -0.53 | 1066 | REJECT |
| BollingerSqueeze | -0.60 | 762 | REJECT |
| LiquiditySweep | -0.52 | 2763 | REJECT |
| VolumeBreakout_2.0 | -0.49 | 78 | REJECT |
| RSI_25_75 | -0.82 | 585 | REJECT |
| RSI_30_70 | -0.36 | 1264 | REJECT |

### Label-shuffle on best single-asset pockets

| Case | OOS Sharpe | p-value | Verdict |
|------|------------|---------|---------|
| Donchian_10 XAUUSD | +0.14 | 0.375 | NO_EDGE |
| Donchian_20 XAUUSD | +0.18 | 0.345 | NO_EDGE |
| Donchian_55 NAS100 | -0.18 | 0.740 | NO_EDGE |
| Momentum126 NAS100 | +0.48 | 0.255 | NO_EDGE |
| Hybrid60 NAS100 | +0.33 | 0.295 | NO_EDGE |

**Survives: NONE** — every positive single-asset Sharpe is noise.

---

## What must be true before this ensemble can be tested

1. **MTM/MRB indicators must be wired** into BacktestEngine or computed inline by the strategies — currently 0 signals, 0 testable
2. **Ensemble weights must be derived from OOS data** (currently manually assigned per `ALPHA_COMBINATION_AUDIT.md:11`)
3. **Ensemble must pass pooled DK-test** with the same `dk_t > 2.0 AND pos_sharpe ≥ 5` bar as individual strategies
4. **Label-shuffle must survive** at ensemble level
5. **Cost stress matrix** (0.5x–5x) must show edge survives

Until all 5 conditions are met, this ensemble is a **design hypothesis**, not a trading system.

---

## Recommendations

### If continuing ensemble research (Path B)

1. Wire MTM/MRB indicators into BacktestEngine (or rewrite strategies to compute inline)
2. Run edge search on the ensemble with wired indicators
3. Pre-register weight derivation method before seeing results
4. Only then: pooled DK → label-shuffle → cost stress → holdout (once)

### If stopping (Path A)

Archive this document as "design not implemented". The individual strategies that DO produce signals (RSI, Donchian, HybridMomMR, Momentum12M, VolumeBreakout) all REJECT on D1 pooled. The ensemble's two primary components (MTM, MRB) can't even generate signals. There is no ensemble edge to build on.

---

*Generated: 2026-07-18*
*Honest note: This document replaces the previous "✅ validated" version which contained claims not supported by any test artifact.*
