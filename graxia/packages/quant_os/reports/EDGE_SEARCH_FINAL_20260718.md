# EDGE SEARCH FINAL — 2026-07-18

**Method:** Pre-registered pooled DK-test + label-shuffle (no sacred holdout burn)  
**Verdict:** **NO STRATEGY HAS PROVEN EDGE — LIVE = NO GO**

---

## What We Ran

### 1. Unified D1 pooled DK-test (`scripts/edge_search_all.py`)

- Universe: XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30 (BTC excluded — known max_dd artifact)
- Costs: Pepperstone Razor-style spread + commission (same as prior pooled tests)
- GO rule (pre-registered): `dk_t > 2.0 AND positive_sharpe_count >= 5`
- Strategies tested: **17** (RSI ×3, Donchian ×4, BollingerSqueeze, Momentum12M ×2, HybridMomMR ×2, VolumeBreakout ×2, LiquiditySweep, MRB, MTM)

### 2. Label-shuffle on best single-asset pockets (`scripts/label_shuffle_top.py`)

- 200 shuffles each
- OOS = last 20% of sample
- Survive rule: `p < 0.05 AND oos_sharpe > 0`

### 3. H1 exploratory scan (partial — XAUUSD complete)

- Not used for GO decision (exploratory only)

---

## Results — D1 Pooled Ranking

| Rank | Strategy | Trades | DK-t | Pooled Sharpe | Pos | Verdict |
|------|----------|--------|------|---------------|-----|---------|
| 1 | RSI_20_80 | 214 | **-0.22** | -0.61 | 0/6 | REJECT |
| 2 | RSI_30_70 | 1264 | **-0.36** | -0.59 | 0/6 | REJECT |
| 3 | Momentum12M_252 | 3548 | **-0.39** | -0.47 | 2/6 | REJECT |
| 4 | HybridMomMR_20 | 3648 | **-0.41** | -0.48 | 1/6 | REJECT |
| 5 | HybridMomMR_60 | 3706 | **-0.42** | -0.49 | 1/6 | REJECT |
| 6 | VolumeBreakout_2.0 | 78 | **-0.49** | -1.98 | 0/3 | REJECT |
| 7 | LiquiditySweep | 2763 | **-0.52** | -0.65 | 0/7 | REJECT |
| 8 | Momentum12M_126 | 3591 | **-0.52** | -0.61 | 1/6 | REJECT |
| 9 | DonchianADX_10_25 | 1066 | **-0.53** | -0.87 | 2/6 | REJECT |
| 10 | Donchian_55 | 1102 | **-0.59** | -0.97 | 2/6 | REJECT |
| 11 | BollingerSqueeze_p20 | 762 | **-0.60** | -1.09 | 0/6 | REJECT |
| 12 | Donchian_10 | 2293 | **-0.61** | -0.82 | 1/6 | REJECT |
| 13 | Donchian_20 | 1771 | **-0.75** | -1.03 | 2/6 | REJECT |
| 14 | VolumeBreakout_1.5 | 97 | **-0.77** | -2.80 | 0/4 | REJECT |
| 15 | RSI_25_75 | 585 | **-0.82** | -1.15 | 0/6 | REJECT |
| — | MRB_default | 0 | — | — | — | NO SIGNALS (needs indicators) |
| — | MTM_default | 0 | — | — | — | NO SIGNALS (needs MTF indicators) |

**GO: NONE**  
**MARGINAL: NONE**  
**Every strategy with trades has negative DK t-stat.**

Artifacts:
- `reports/edge_search_all_results.json`
- `reports/edge_search_all_run.log`

---

## Single-Asset Pockets (looked interesting, then failed)

These had **positive per-asset Sharpe** in the pooled run — classic multiple-testing traps:

| Strategy | Symbol | Trades | Sharpe | PF | Total ret |
|----------|--------|--------|--------|-----|-----------|
| Donchian_10 | XAUUSD | 480 | +1.17 | 1.20 | +20% |
| Donchian_55 | NAS100 | 97 | +1.41 | 1.21 | +4.7% |
| Momentum12M_126 | NAS100 | 231 | +1.13 | 1.17 | +8.8% |
| HybridMomMR_60 | NAS100 | 227 | +0.85 | 1.12 | +6.5% |
| Momentum12M_252 | NAS100 | 216 | +0.65 | 1.09 | +4.6% |

### Label-shuffle verdict (200 iterations)

| Case | OOS Sharpe | p-value | null p95 | Verdict |
|------|------------|---------|----------|---------|
| Donchian_10 XAUUSD | +0.14 | **0.375** | 0.61 | **NO_EDGE** |
| Donchian_20 XAUUSD | +0.18 | **0.345** | 0.63 | **NO_EDGE** |
| Donchian_55 NAS100 | -0.18 | **0.740** | 0.94 | **NO_EDGE** |
| Momentum126 NAS100 | +0.48 | **0.255** | 0.96 | **NO_EDGE** |
| Hybrid60 NAS100 | +0.33 | **0.295** | 0.79 | **NO_EDGE** |

**Survives: NONE**

Artifact: `reports/label_shuffle_top_results.json`

---

## H1 Exploratory (XAUUSD only — partial run)

| Strategy | Trades | PnL | PF | Trade-Sharpe |
|----------|--------|-----|-----|--------------|
| Momentum12M_126 | 1654 | +1585 | 1.07 | 0.62 |
| HybridMomMR_60 | 1670 | +1012 | 1.05 | 0.41 |
| DonchianADX_10_25 | 773 | +78 | 1.01 | 0.07 |
| RSI_20_80 | 144 | +32 | 1.02 | 0.06 |
| Donchian_10 | 1406 | -100 | 1.00 | -0.01 |
| Donchian_20 | 1120 | -705 | 0.95 | -0.31 |

Best H1 pocket (Momentum126 XAU) has PF 1.07 / Sharpe 0.62 — **below any honest GO bar**.  
EURUSD H1 showed catastrophic PnL (engine sizing/tick artifact on FX — do not trust until fixed).

---

## Strategies NOT Testable on This Harness (need external data)

These exist in `strategies/` but cannot run on single-asset OHLCV D1 alone:

| Strategy | Why blocked |
|----------|-------------|
| RYDC | Needs DXY + real-yield (DFII10) |
| VolRiskPremium | Needs GVZ / implied vol |
| COT positioning | Needs CFTC COT |
| FOMC drift | Needs event calendar + rates |
| Gold-Silver spread | Needs pair series |
| Cross-asset momentum / vol rank | Needs multi-asset panel |
| Funding rate arb | Needs crypto funding |
| Orderflow imbalance | Needs tick/L2 |
| Session pattern | Needs H1+ session timestamps (function API, not Strategy class) |
| MLB / MLMR | Needs trained ML model |

**Honest status:** UNKNOWN (not REJECT, not GO). Next research track if continuing.

---

## QA Corrections (from reconciliation audit)

### 1. Denominator mismatch explained

RSI variants show `pos_sharpe 0/6` while LiquiditySweep shows `0/7` — this is NOT a data error. The engine's `InlineContractSpec.for_symbol()` fallback returns default `tick_size=0.01, contract_size=100` for unrecognised symbols. RSI strategies sometimes fail to generate ANY signal on US30 (0 trades, excluded from positive-sharpe count), while LiquiditySweep trades US30 once (1 trade, included). The "total_assets" field counts assets that produced **any trade** (≥1), not the full universe.

| Strategy | US30 trades | XAGUSD trades | Panel size |
|----------|-------------|---------------|------------|
| RSI_20_80 | 0 | 1 | 6 |
| RSI_25_75 | 0 | 0 → 5 | 5–6 |
| LiquiditySweep | 1 | 365 | 7 |

All DK t-stats remain negative regardless. **No conclusion changes.**

### 2. VolumeBreakout low trade count — root cause

VolumeBreakout trades are scarce (78/97) because **EURUSD D1 has only 14 bars with volume > 0** out of 14,220 rows. GBPUSD has 18, USDJPY 254. The volume confirmation condition (`current_volume > volume_sma × threshold`) filters out >99.8% of bars on most FX pairs. This is legitimate — VolumeBreakout is data-dependent on instruments with reported volume (indices, crypto, metals). **Not a sizing bug.**

### 3. EURUSD max_dd_pct > 10000% — tick_size fallback artifact

EURUSD, GBPUSD, XAGUSD show `max_dd_pct` in the thousands. This is caused by `InlineContractSpec.for_symbol()` returning default `trade_tick_size=0.01, trade_tick_value=1.0` for some symbols in the pooled harness — wrong contract specs → massive position sizing → huge drawdown %. **These per-asset numbers are unreliable for the affected symbols, but pooled DK t-stat (which aggregates daily returns, not per-asset DD) is unaffected.**

---

## Go / No-Go

| Decision | Status |
|----------|--------|
| Paper trade any of the 17 tested strategies as "edge" | **NO GO** |
| Live capital on any tested strategy | **NO GO** |
| Auto live mode | **NO GO** |
| Infrastructure (risk/kill/OMS) | Separate — improved, not the blocker |
| Sacred holdout (`holdout_fresh_20260717.csv`) | **STILL LOCKED — do not burn** |

---

## Why This Is Not "We Need More Tuning"

1. **All DK t-stats negative** — not "close to 2.0"; systematically below zero after costs  
2. **Label-shuffle p-values 0.25–0.74** — positive single-asset Sharpes are noise  
3. **Prior campaigns (TSMOM, Donchian, RSI, Bollinger) already REJECT** — this run reconfirmed + expanded  
4. **Parameter tweaking after seeing results = p-hacking** — Constitution forbids

---

## Recommended Paths (pick one)

### Path A — Stop / Pivot (recommended if capital preservation first)
- Archive D1 classic TA as **NO EDGE after costs**
- Do not open auto live
- Keep infra for when a real hypothesis exists

### Path B — New hypothesis class (research, not live)
1. Build **cross-asset / macro** tests (RYDC, COT, DXY divergence) with pre-registered params  
2. Or **session-aware H1** with pre-registered London/NY rules (not free parameter search)  
3. Pre-register ONE hypothesis → run DK → label-shuffle → only then touch holdout once  
4. Minimum GO bar stays: `dk_t > 2.0`, multi-asset, cost-stressed, label-shuffle p < 0.05

### Path C — External edge import
- Port a strategy with **published, peer-reviewed, cost-adjusted** evidence (e.g. classic TSMOM futures literature) onto futures/CFD with correct contract specs  
- Still re-validate on this engine with DK + costs — do not trust papers blindly

---

## Scripts Added This Session

| Script | Purpose |
|--------|---------|
| `scripts/edge_search_all.py` | Unified D1 pooled DK across all single-asset strategies |
| `scripts/edge_search_h1.py` | H1 exploratory single-asset scan |
| `scripts/label_shuffle_top.py` | Label-shuffle on best D1 pockets |

---

## One-Sentence Truth

> After testing 17 strategies on multi-asset D1 with realistic costs and label-shuffling the best single-asset pockets, **no strategy separates from noise** — the system is not ready to trade for profit; the blocker is edge, not infrastructure.

*Generated: 2026-07-18*  
*Sacred holdout: NOT USED*
