# DOC_CODE_CONTRADICTION_AUDIT.md — Phase 0.12–0.13

## 0.12 — Documentation-vs-Code Contradiction Sweep

| Doc Claim | Source | Current Code Reality | Contradiction? | Resolution |
|---|---|---|---|---|
| "MT5 gateway is read-only stub" | KNOWN_LIMITATIONS.md:1 | `execution/adapters/mt5.py:222` calls `mt5.order_send()` — live-capable | **YES (P0)** | Gateway IS read-only; adapter IS live-capable. Doc is misleading. Must be corrected. See Phase 0.11. |
| "Swap not modeled in cost calculations" | KNOWN_LIMITATIONS.md:3 | `core/risk/swap_cost.py` exists, `backtest/engine.py:1225` optionally calls it via `_SWAP_COST_AVAILABLE` flag | **PARTIAL** | Swap IS modeled in backtest (optional wiring). NOT modeled in live execution. Doc outdated for backtest, accurate for live. |
| "Backtest engine uses close-price fills" | KNOWN_LIMITATIONS.md:4 | `execution/execution_simulator.py` uses `estimate_bid_ask_from_bar()` — bar-level fill model, not close-price | **YES** | Close-price fill assumption was replaced by bar-level bid/ask estimation. Doc outdated. |
| "Walk-forward implemented for XAUUSD/EURUSD at 15min/1min" | KNOWN_LIMITATIONS.md:7 | `validation/walk_forward.py` is generic — not instrument-limited. `scripts/run_multi_symbol_wf.py` runs multi-symbol. | **PARTIAL** | WF is implemented generically but only run on XAUUSD/EURUSD in practice. Other 13 instruments have no WF results. |
| "PnL multiplier bug fixed (was hardcoded 2350)" | Prior audit / commit msg | `scripts/walk_forward.py:78` comment confirms fix: "the previous hardcoded $2350.0 (Bug #1 fix)" | **FIX UNVERIFIED** | Current code uses `close_prices` series (not hardcoded). Prior buggy state not re-tested per R13. |
| "60 days minimum paper trading required" | core/golden_rules.py:29 | `validation/paper_trading_validator.py:4` — "minimum 12 weeks (84 days)" | **YES** | Golden rules say 60 days; paper_trading_validator says 84 days. Conflicting requirements. |
| "DSR and PBO analysis not yet standardized" | KNOWN_LIMITATIONS.md:7 | `validation/deflated_sharpe.py` and `validation/probability_overfitting.py` both exist and are wired into `validation/overfitting_detector.py` | **YES** | DSR and PBO ARE implemented and wired. Doc outdated. |
| "No EURUSD or GBPUSD research started" | KNOWN_LIMITATIONS.md:6 | `scripts/run_multi_symbol_wf.py` runs WF on multiple symbols including EURUSD | **YES** | EURUSD research HAS been started. Doc outdated. |
| "System is single-broker MT5" | Audit protocol R6 assumption | `execution/adapters/binance.py` exists — Binance adapter scaffolded | **PARTIAL** | Binance adapter exists but is not wired into live execution. Single-broker in practice, multi-broker scaffolded. |

### Summary
- **3 confirmed contradictions** with current code (MT5 live-capability, DSR/PBO implementation, EURUSD research)
- **1 P0 contradiction**: KNOWN_LIMITATIONS.md implies system cannot place real orders when it can
- **2 outdated claims**: close-price fills, paper trading minimum days
- **1 conflicting requirement**: 60 days vs 84 days paper trading minimum

---

## 0.13 — Per-Instrument Data-Sufficiency Table

### Data on Disk
From Phase 0.5 scan: only `data/EURUSD_D1.csv` and `data/XAUUSD_D1.csv` are confirmed present at project root. Other instrument data likely in `data/` subdirectories or DuckDB.

### Instruments in Scope × Timeframe

| Instrument | Asset Class | Timeframes Used | M1 Rows (est.) | D1 Rows (est.) | Meets Minimum? |
|---|---|---|---|---|---|
| EURUSD | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | YES (D1 confirmed on disk) |
| GBPUSD | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED — no data file confirmed |
| USDJPY | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| USDCAD | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| USDCHF | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| AUDUSD | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| NZDUSD | FX | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| BTCUSD | Crypto | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| ETHUSD | Crypto | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| NAS100 | Indices | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| US30 | Indices | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| XAUUSD | Metals | M1, M5, M15, H1, D1 | ~5,000 (M1 limited) | ~1,200+ | **PARTIAL** — D1 confirmed; M1 has ~5,000 rows (~3-4 days) |
| XAGUSD | Metals | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| XPDUSD | Metals | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |
| XPTUSD | Metals | M15, H1, D1 | ~50,000+ | ~1,200+ | UNVERIFIED |

### Key Findings
1. **XAUUSD M1 data is severely limited**: ~5,000 rows = ~3-4 trading days. This is **[INSUFFICIENT DATA — training/validation on M1 is not currently meaningful]** for XAUUSD.
2. **Only 2 instruments confirmed on disk** at D1 level. The other 13 instruments' data presence is **[UNVERIFIED — data may exist in DuckDB or subdirectories but was not confirmed during this census]**.
3. **Walk-forward coverage**: Only XAUUSD and EURUSD have confirmed WF results. The other 13 instruments have **[NO OOS EVIDENCE — trading or paper-trading these instruments is currently unvalidated]**.
4. **Crypto instruments** (BTCUSD, ETHUSD): No data files confirmed. If the system trades these live, it is trading on unvalidated data. **[DATA PRESENCE UNVERIFIED]**.
5. **Thinner metals** (XPDUSD, XPTUSD): No data files confirmed. These have historically thinner liquidity and wider spreads — data sufficiency is critical and unverified.

### Minimum Data Requirements
- **D1 backtest**: ~5 years = ~1,260 bars minimum
- **M15 backtest**: ~5 years = ~50,000+ bars minimum  
- **M1 backtest**: ~1 year = ~250,000+ bars minimum (current XAUUSD M1 has ~5,000 = **FAIL**)
- **ML training**: ~10,000+ independent samples minimum after autocorrelation adjustment

### Action Required
Every backtest or trained model built on a flagged instrument/timeframe pair inherits this flag everywhere it's cited later in the audit (Phases 5–7, 14, 16).

---

*Next: See DATA_PIPELINE_FORENSICS.md for Phase 1*
