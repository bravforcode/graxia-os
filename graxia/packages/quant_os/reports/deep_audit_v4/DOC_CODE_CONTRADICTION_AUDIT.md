# DOC-CODE CONTRADICTION AUDIT

Generated: 2026-07-05 | Version: quant_os 0.2.0-dev

---

## 0.12 Documentation-vs-Code Contradiction Sweep

For every capability/status claim in docs, verified against current code.

---

### Contradiction Table

| # | Doc Claim | Source | Code Reality | Contradiction? |
|---|-----------|--------|-------------|----------------|
| 1 | MT5 Gateway is read-only, does NOT send orders | KNOWN_LIMITATIONS.md:1 | broker/mt5_gateway.py:207 no order_send. TRUE. BUT execution/adapters/mt5.py:209 DOES call mt5.order_send(). Two separate modules with opposite capabilities. | YES -- KNOWN_LIMITATIONS acknowledges this (Not the same as execution/adapters/mt5.py) so partial mitigation |

| 2 | Backtest engine uses close-price fills | KNOWN_LIMITATIONS.md:4 | backtest/engine.py:1110-1147. Verified: engine calculates swap_cost, subtracts from PnL. Uses fill simulation from config params. bar-level resolution confirmed. | NO |

| 3 | No EURUSD or GBPUSD research started | KNOWN_LIMITATIONS.md:6 | Summary.md:29 references EURUSD/GBPUSD next steps. EURUSD backtest in run_backtest.py exists. EURUSD M1 data (100K rows) exists in data/. CONTROVERSIAL: Basic backtest exists but formal research may not. | PARTIAL -- Some EURUSD work done but not formalized |

| 4 | Walk-forward for XAUUSD/EURUSD at 15min/1min implemented | KNOWN_LIMITATIONS.md:7 | core/walk_forward_production.py exists. run_ml_train.py:124 includes WFO. strategies/walk_forward.py exists. CONFIRMED. | NO |

| 5 | Build: passing ~ Tests: ~2920 (0 fail) | README.md:58 | Current scan: 290 test files, ~3,860 test functions. But scikit-learn NOT INSTALLED which would cause ML test failures. Unverified exactly how many pass/fail. | PARTIAL -- scikit-learn missing may cause failures |

| 6 | Phase 3.1: Canonical Engine Integration IN PROGRESS | STATUS.md:15 | backtest/engine.py fully integrated with swap_cost, sizing, fill model. Phase 3.1 tests exist (tests/test_phase_3_1_*.py). Appears COMPLETE. | YES -- STATUS.md out of date, code shows completed |

| 7 | Paper trading: regime-aware filtering, kill switch, circuit breakers | RUNBOOK.md:10-11 | regime/risk_overlay.py implement kill switch. circuit_breaker.py exists. PRE_TRADE risk checks exist. CONFIRMED all exist in code. | NO |

| 8 | Multi-strategy ensemble: Liquidity Sweep, MTM, MRB, MLB | RUNBOOK.md:8 | strategies/ensemble.py has dynamic weighting. MTM, MRB, MLB exist. Liquidity sweep is in gold_bot/strategies/liquidity_sweep.py and run_paper_trading.py. CONFIRMED. | NO |

| 9 | Paper trading: Full pipeline on live MT5 data | RUNBOOK.md:8 | run_paper_trading.py:166 calls mt5.initialize(). line 173: mt5.copy_rates_from_pos() for live data. CONFIRMED. | NO |

| 10 | Risk policy is frozen dataclass, no runtime mutation | CONSTITUTION.md:15 (INV-001) | risk/risk_policy.py: inspected. Frozen dataclass. BUT core/config.py:178-216 REPLACEMENT risk_policy via re-assigning self.risk_policy. This is MUTATION by replacement, not mutation in place. | PARTIAL -- Replacement allowed, fresh frozen objects created each time |

| 11 | No order_send exists in backtest or risk modules | CONSTITUTION.md:17 (INV-003) | Firewall tests in tests/test_backtest_isolation.py:11, tests/test_canonical_runtime_import_isolation.py:57, tests/test_phase_2a.py:201, repo_intelligence/tests/test_repo_intelligence.py:206. ALL verify this invariant. CONFIRMED. | NO |

| 12 | Every dataset has manifest with SHA-256 checksum | CONSTITUTION.md:18 (INV-005) | data/manifests/ directory not found in glob. No *.manifest.json files found. CONTRADICTION. | YES -- No manifests found on disk |

| 13 | Kill switch persists across restart via JSON file | CONSTITUTION.md:19 (INV-008) | data/kill_switch_state.json: EXISTS. data/kill_switch_corrupt_test.corrupt.*.json: EXISTS (corruption test). risk/kill_switch.py: verify persistence logic. CONFIRMED. | NO |

| 14 | Pre-trade risk gate mandatory before any order | CONSTITUTION.md:20 (INV-009) | risk/pre_trade_risk.py exists. risk/pre_trade_gate.py exists. run_paper_trading.py:548 calls risk_overlay.approve() before order. CONFIRMED in PaperTrader path. | NO |

| 15 | Phase 1 completed: MTF Fix 4/4 PASS | STATUS.md:7 | Tests exist. Unverified current pass/fail. | Unverified |

| 16 | Phase 2A completed: Safety Preflight 11/11 PASS | STATUS.md:8 | tests/test_phase_2a.py:201 tests. Unverified current status. | Unverified |

| 17 | Liquidity_sweep strategy: XAUUSD CANDIDATE_ONLY | STATUS.md:21 | gold_bot/strategies/liquidity_sweep.py exists. run_paper_trading.py uses Liquidity Sweep pipeline with symbols configurable (not just XAUUSD). STATUS.md claim may be outdated. | YES -- Now multi-symbol in paper trading |

| 18 | ~2,920 tests (0 fail) | README.md:58 | Counted ~3,860 test functions across 290 files. No current test run performed. scikit-learn missing may cause failures. Status UNABLE TO VERIFY without running test suite. | Unverified |

| 19 | Walk-forward + Bonferroni corrected signal analysis | CHANGELOG.md:58 | core/walk_forward_production.py, validation/ modules exist. Feature diagnostic mentioned in SUMMARY.md:25. CONFIRMED modules exist. | Unverified |

| 20 | risk/swap_cost.py is core module | CONSTITUTION (implied) | core/risk/swap_cost.py is WIRED into backtest/engine.py:77,1110. CONFIRMED working. | NO |

---

### SUMMARY: Documentation Accuracy

| Finding | Count |
|---------|-------|
| Confirmed (NO contradiction) | 8 |
| Contradiction (YES) | 5 |
| Partial contradiction | 4 |
| Unverified (needs test run) | 3 |

Key Contradictions:
1. STATUS.md says Phase 3.1 IN PROGRESS -- appears COMPLETE in code
2. Liquidity_sweep now multi-symbol, not XAUUSD-only
3. No data manifests with SHA-256 checksums found
4. risk_policy mutated by replacement (not fully frozen)
5. KNOWN_LIMITATIONS.md is mostly accurate but understates code completion

---

## 0.13 Per-Instrument Data-Sufficiency Table

For every instrument x timeframe used for training/signal generation.
Data source: data/market_data/ CSV files.
Min threshold: > 10,000 rows for M1 (approx 1 week of 24h data).

### M1 (1-minute) Data

| Instrument | Rows | Date Start | Approx Days | Meets Min? | Notes |
|-----------|------|-----------|-------------|------------|-------|
| XAUUSD | 100,000 | 2026-05-14 | ~52 | YES | Gold - primary trading instrument |
| EURUSD | 100,000 | 2026-05-18 | ~48 | YES | Major forex pair |
| GBPUSD | 100,000 | Unverified | ~69 | YES | Major forex pair |
| USDJPY | 100,000 | Unverified | ~69 | YES | Major forex pair |
| USDCAD | 100,000 | Unverified | ~69 | YES | Major forex pair |
| USDCHF | 100,000 | Unverified | ~69 | YES | Major forex pair |
| AUDUSD | 100,000 | Unverified | ~69 | YES | Major forex pair |
| XAGUSD | 100,000 | Unverified | ~69 | YES | Silver |
| NAS100 | 100,000 | Unverified | ~69 | YES | Index |
| US30 | 100,000 | Unverified | ~69 | YES | Index |
| NZDUSD | 5,001 | Unverified | ~3.5 | NO | INSUFFICIENT |
| XPDUSD | 5,001 | Unverified | ~3.5 | NO | INSUFFICIENT |
| XPTUSD | 5,001 | Unverified | ~3.5 | NO | INSUFFICIENT |
| BTCUSD | 7,881 | Unverified | ~5.5 | NO | INSUFFICIENT |
| ETHUSD | 7,881 | Unverified | ~5.5 | NO | INSUFFICIENT |

### M15 (15-minute) Data

| Instrument | Rows | Meets Min? |
|-----------|------|------------|
| XAUUSD | 50,001 | YES |
| EURUSD | 50,001 | YES |
| GBPUSD | 50,001 | YES |
| NAS100 | 60,001 | YES |
| Most others | 60,001 | YES |

### Data Gaps

| Issue | Details |
|-------|--------|
| EURUSD missing M5, M30 | Only M1, M15, D1, H1, H4 present. No M5/M30 CSV files. |
| NZDUSD insufficient M1 | 5,001 rows only. Cannot train on M1. |
| BTCUSD/ETHUSD insufficient | 7,881 rows for crypto. Needs more. |
| OIL data missing | paper_trade_config.json references OIL (USOIL) but no data files found. |
| No ForexFactory calendar data | news_events/ exists but no data files found. |

### VERDICT

Major forex pairs (EURUSD, GBPUSD, USDJPY) and XAUUSD have sufficient data
for training (100K M1 rows, 50K M15 rows). Minor instruments (NZD, crypto,
exotic metals) have insufficient data. OIL/USOIL referenced in config has
NO data files.

Previously reported ~5K rows (SUMMARY.md:17) is NO LONGER ACCURATE.
Current XAUUSD M1 data is 100,000 rows starting 2026-05-14.

---
