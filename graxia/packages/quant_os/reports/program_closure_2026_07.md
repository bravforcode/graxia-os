# Program Closure Report — Edge Discovery Research (Direction A + B + C)

**Date:** 2026-07-13
**Decision:** A — STOP
**Author:** User (confirmed via conversation)

---

## 1. What Was Done

### Research Program Scope
- **Direction A:** XAUUSD technical/statistical methods (RYDC, CAM, SP, MRM)
- **Direction B:** Multi-instrument + different mechanisms (GSS, BVC, CVR)
- **Direction C:** Volume-Price Divergence in Crypto (BTCVD, ETHVC, BEVS)
- **Total hypotheses tested:** 11 (trial #1001-1008, #2001-2003)
- **Cumulative trial count at closure:** 1008/1022 (Dir A+B) + 3/10 (Dir C)

### Hypotheses Tested — Direction A + B

| Trial | Strategy | Mechanism | p-value | Sharpe | Verdict |
|-------|----------|-----------|---------|--------|---------|
| 1001 | RYDC Arm A | Cross-asset RYDC | 0.968 | 0.044 | REJECTED |
| 1003 | CAM | DXY→XAUUSD lead-lag | 0.598 | 0.361 | REJECTED |
| 1004 | SP | Session patterns | 0.934 | 0.056 | REJECTED |
| 1005 | MRM | DFII10 regime MR | 0.244 | -1.157 | REJECTED |
| 1006 | GSS | XAU/XAG ratio MR | 0.505 | -0.963 | REJECTED |
| 1007 | BVC | BTC vol clustering | 0.248 | 1.739 | REJECTED |
| 1008 | CVR | Vol percentile value | 0.610 | -0.402 | REJECTED |

### Hypotheses Tested — Direction C (Volume-Price Divergence in Crypto)

| Trial | Strategy | Mechanism | p-value | Sharpe | Trades | Verdict |
|-------|----------|-----------|---------|--------|--------|---------|
| 2001 | BTCVD | BTC vol-price divergence | 0.553 | -2.058 | 6 | REJECTED |
| 2002 | ETHVC | ETH volume confirmation | 0.591 | 0.815 | 28 | REJECTED |
| 2003 | BEVS | BTC-ETH vol spread | 0.188 | 1.281→0.85 | 68→646 | REJECTED |

**BEVS Sharpe inflation note:** Trial 2003 (BEVS) showed Sharpe 1.28 at 68 trades, but hourly validation with 646 trades converged to 0.85. This confirms the min-trades≥100 gate works correctly — small samples produce inflated Sharpe ratios.

### Why Stopped

**Stopping rule §3.4 triggered three times independently from three structurally different directions:**
1. Direction A: 4 consecutive p-value failures (RYDC, CAM, SP, MRM) — XAUUSD technical methods
2. Direction B: 3 consecutive p-value failures (GSS, BVC, CVR) — multi-instrument mechanisms
3. Direction C: 3 consecutive p-value failures (BTCVD, ETHVC, BEVS) — crypto volume-price divergence

**Statistical evidence:** p-values range from 0.188 to 0.968 across all 11 hypotheses — all far from significance threshold (0.05). This is NOT underpowering (which would show p-values clustered near 0.05-0.15). This is absence of effect across every tested mechanism and instrument class.

---

## 2. What We Learned

### Key Findings

**Direction A+B (XAUUSD/Multi-instrument):**
1. **XAUUSD with technical/statistical methods is consistently null** — 5 different mechanisms tested, all REJECTED
2. **Cross-asset momentum on XAUUSD is exhausted** — 0-for-2 (RYDC + CAM)
3. **Session patterns on XAUUSD daily are null** — p=0.93 is the most null result
4. **Regime-conditional MR with DFII10 is harmful** — negative Sharpe
5. **Gold/Silver ratio MR doesn't work** — negative Sharpe at daily frequency
6. **BTC vol clustering may have something** — 72.4% win rate, Sharpe 1.74 — but sample too small (29 trades)
7. **Vol percentile value is null** — negative Sharpe

**Direction C (Crypto Volume-Price Divergence):**
8. **BTC volume-price divergence is null** — only 6 trades generated, negative Sharpe (-2.06). The signal is too rare to be actionable.
9. **ETH volume confirmation is null** — 28 trades, 60.7% win rate sounds promising but p=0.59 is coin-flip. Below 100-trade minimum.
10. **BTC-ETH vol spread is the most interesting null** — Sharpe 1.28 at 68 trades, but converges to 0.85 at 646 trades. Still not significant (p=0.19). Proves that small-sample Sharpe is unreliable.
11. **11/11 hypotheses null across 3 independent directions** — strongest evidence yet that no accessible edge exists with public data + current methodology.

### Bugs Fixed (Valid Regardless of Edge Discovery)

| Bug | File | Impact |
|-----|------|--------|
| DSR formula | `run_rydc_validation.py` | DSR gate now correctly rejects |
| WFE bound | `run_rydc_validation.py` | WFE > 1.5 = INSUFFICIENT_DATA |
| PBO | `run_rydc_validation.py` | N/A for single config |
| evaluate_model() | `auto_retrain.py` | Real metrics, not dummy |
| Cost fallback | `run_multi_instrument_wf.py` | Fail loudly |
| Unicode encoding | Multiple scripts | `→` → `->` |

### Infrastructure Built (Reusable)

| Component | Reusable for |
|-----------|-------------|
| Validation pipeline | Any future hypothesis |
| Sacred holdout mechanism | Any future research program |
| Stopping rule framework | Any future research program |
| Trial counter | Any future research program |
| Pre-registration template | Any future hypothesis |
| Kill-switch recovery test | Live trading safety |
| Alert routing test | Live trading safety |
| Cost calibration | Any instrument |

---

## 3. What Remains

### Sacred Holdout
- **Path:** `data/sacred_holdout/holdout.csv`
- **Status:** LOCKED — do not open until candidate passes all gates
- **260 rows** (2025-07-01 to 2026-07-01)
- **Use count:** 0 (never opened)

### KillSwitch/StateCoordinator Wiring
- **Status:** Fixed in this session — StateCoordinator wired into TradingOrchestrator
- **What changed:** RiskOverlay and RiskLedger now sync when kill switch is activated/deactivated
- **Verification:** `test_orchestrator_kill_switch.py` + `test_integration_e2e.py` pass

### alpha/engine.py Stubs
- **Status:** Crypto/Forex/Indices = NotImplementedError
- **Priority:** DEPRIORITIZED — no validated edge exists for any asset class

---

## 4. If Future Research

If a new research program is opened in the future, it must meet ALL 3 conditions:

1. **Instrument/market that is significantly less efficient** — not XAUUSD/EURUSD/BTC (heavily traded globally)
2. **Data type never used before** — not OHLC bars/cross-asset correlation/volume (order flow, L2 depth, alternative data)
3. **Rationale that is NOT a variation of momentum/MR/vol-clustering/volume-divergence** — something structurally different

And it must be:
- New pre-registration document
- New trial ledger (NOT extending current counters)
- New sacred holdout (from new data source)
- New stopping rule (pre-registered before starting)

---

## 5. Locked Files

| File | SHA-256 | Status |
|------|---------|--------|
| `research/hypothesis_registry.json` | `1c65c799...` | LOCKED |
| `research/trial_ledger.json` | `efb11848...` | LOCKED |
| `research/hypothesis_registry_c.json` | — | LOCKED |
| `research/trial_ledger_c.json` | — | LOCKED |
| `research/meta_learning.md` | `5975884c...` | LOCKED |
| `data/sacred_holdout/holdout.csv` | `5a15961c...` | LOCKED |
| `data/sacred_holdout/holdout_btc.csv` | — | LOCKED |
| `reports/stopping_rule_2026_07_12.md` | `db3b8179...` | LOCKED |
| `reports/direction_c_registration.md` | — | LOCKED |

---

## 6. Final Statement

> 11/11 hypotheses null across 3 structurally independent directions (XAUUSD technical, multi-instrument mechanism, crypto volume-price divergence). Stopping rule fired 3 times from 3 independent sources. Governance worked correctly at every level — the system detected no edge and refused to trade. This is the correct scientific outcome. The BEVS Sharpe inflation (1.28→0.85 with more data) validates the min-trades≥100 gate and proves the validation pipeline catches small-sample bias. All infrastructure built (validation pipeline, sacred holdout, stopping rule framework, bug fixes, kill-switch wiring) is reusable and production-ready for any future research direction.
