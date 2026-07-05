# DOC-CODE CONTRADICTION AUDIT
**Phase 0.12–0.13 | 2026-07-05**

---

## 0.12 — Documentation-vs-Code Contradiction Sweep

| Doc Claim | Source | Current Code Reality | Contradiction? | Resolution |
|---|---|---|---|---|
| "MT5 gateway is read-only stub" | `KNOWN_LIMITATIONS.md:1` | `execution/adapters/mt5.py:195` has `submit_order()` calling `mt5.order_send()` | **YES — P0** | See 0.11 |
| "Swap not modeled in cost calculations" | `KNOWN_LIMITATIONS.md:3` | `core/risk/swap_cost.py` exists with full implementation | **PARTIAL** — module exists but not wired | Module is orphaned per R19 |
| "Backtest engine uses close-price fills" | `KNOWN_LIMITATIONS.md:4` | `backtest/engine.py` uses `ExecutionSimulator` with bid/ask estimation from bars, slippage model, and market impact | **PARTIAL** — improved but not tick-level | Bar-level fills with slippage model; tick-level pending |
| "Walk-forward implemented for XAUUSD/EURUSD" | `KNOWN_LIMITATIONS.md:7` | `scripts/walk_forward.py` accepts `--symbol` flag for any instrument | **PARTIAL** — code supports any symbol, but only 2 validated | Coverage gap confirmed |
| "No EURUSD or GBPUSD research started" | `KNOWN_LIMITATIONS.md:6` | Data files exist (`EURUSD_M1.csv`, `GBPUSD_M1.csv`), walk_forward.py supports them | **OUTDATED** — data present, research may have started | Doc needs update |
| PnL multiplier bug fixed (was 2350) | Prior audit / commit msg | `scripts/walk_forward.py:88` still has `price_mult = 2350.0` | **PARTIAL** — raw PnL fixed, cost calc still uses 2350 | See Phase 3.8 |

---

## 0.13 — Per-Instrument Data-Sufficiency Table

**M1 Data Row Counts (all instruments):**

| Instrument | M1 Rows | Date Range (est.) | Sufficient for ML Training? |
|---|---|---|---|
| EURUSD | 5,001 | ~3-4 days | **NO** |
| GBPUSD | 5,001 | ~3-4 days | **NO** |
| USDJPY | 5,001 | ~3-4 days | **NO** |
| USDCAD | 5,001 | ~3-4 days | **NO** |
| USDCHF | 5,001 | ~3-4 days | **NO** |
| AUDUSD | 5,001 | ~3-4 days | **NO** |
| NZDUSD | 5,001 | ~3-4 days | **NO** |
| BTCUSD | 7,882 | ~5-6 days | **NO** |
| ETHUSD | 7,882 | ~5-6 days | **NO** |
| NAS100 | 5,001 | ~3-4 days | **NO** |
| US30 | 5,001 | ~3-4 days | **NO** |
| XAUUSD | 5,001 | ~3-4 days | **NO** |
| XAGUSD | 5,001 | ~3-4 days | **NO** |
| XPDUSD | 5,001 | ~3-4 days | **NO** |
| XPTUSD | 5,001 | ~3-4 days | **NO** |

**Verdict:** All 15 instruments at M1 timeframe have **INSUFFICIENT DATA** for meaningful ML training. Minimum recommended: 6 months (~75,000 M1 bars). Current data covers 3-6 days.

**Impact:** Any ML model trained on this data is trained on ~5,000 samples — far below statistical reliability thresholds. Walk-forward validation on this data has extremely high variance and unreliable estimates.

**Note:** Higher timeframes (H1, D1) likely have more rows but were not counted in this pass. The system uses multiple timeframes — D1/H4/H1/M15/M1 data should be verified separately.
