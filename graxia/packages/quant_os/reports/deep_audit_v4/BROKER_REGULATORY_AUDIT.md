# PHASE 11 — BROKER, COUNTERPARTY & REGULATORY AUDIT
**Date**: 2026-07-05 | **Scope**: Full codebase | **Severity Scale**: P0=Critical P1=High P2=Medium P3=Low

---

## 11.1 Broker Identity & Regulatory Status

### Broker(s) Used

| Attribute | Value | Source |
|-----------|-------|--------|
| Primary broker | **IC Markets** (configured) / **Pepperstone** (verified) | `core/config.py:37` vs `Meta/broker_verification_report.md:11` |
| Server | `ICMarkets-Demo02` (configured) | `live_readiness/broker_profile.py:31` |
| Server | `Pepperstone-Demo` (actual credentials) | `Meta/pepperstone_creds.txt.backup:4` |
| Account | 61547941 | `Meta/pepperstone_creds.txt.backup:5` |
| Account type | Razor (raw spread) | `Meta/broker_verification_report.md:18` |
| Platform | MT5 | `Meta/pepperstone_creds.txt.backup:8` |

### ⚠️ CRITICAL: Codebase-Config Discrepancy
- `core/config.py:37` says `primary_broker: str = "ic_markets"`
- `.env.example:9` says `MT5_SERVER=Pepperstone-Demo`
- `live_readiness/broker_profile.py:31` says `expected_server="ICMarkets-Demo02"`
- Actual credentials in `Meta/pepperstone_creds.txt.backup` are for **Pepperstone**
- These three point to different brokers — the codebase is inconsistent about which broker is primary

### Regulation
Pepperstone is regulated by (`Meta/broker_verification_report.md:26-34`):
- **ASIC** (Australia) — AFSL 389931 — Tier 1
- **FCA** (UK) — FRN 684312 — Tier 1
- **CySEC** (Cyprus) — 388/20 — Tier 2
- **SCB** (Bahamas), DFSA (Dubai), CMA (Kenya)

### Execution Model
- **ECN/STP** (Razor account = raw spread + commission)
- **Negative balance protection**: Yes (ASIC-regulated entities)
- **Segregated client funds**: Yes (standard for ASIC/FCA/CySEC)

### Broker Verification Report Status
`Meta/broker_verification_report.md` contains **extensive checklist items marked "⚠️ Pending"** (swap rates, spread verification, lot sizes) — the verification is incomplete.

---

## 11.2 Real-World Cost Schedule Reconciliation

### Spread/Commission: Hardcoded vs Broker

| Source | XAUUSD Spread | EURUSD Commission | Source |
|--------|--------------|-------------------|--------|
| `core/cost_model.py:53` METALS | 12 bps (0.12%) | N/A (metals) | Code |
| `core/cost_model.py:63` FOREX | 1 bps | $7/lot RT | Code |
| `Meta/broker_verification_report.md:54-55` | 0.15-0.30 pips (~0.01 bps) | $7/lot RT | Research |
| `core/config.py:129` (backtest) | — | $3.5/lot (FLAT) | Code |

### ⚠️ CRITICAL FINDING — P1: Backtest commission mismatch
- Code cost model says FOREX commission = **$7/lot** (`core/cost_model.py:63`)
- Backtest config says commission = **$3.5/lot** (`core/config.py:129`)
- Reality: Pepperstone Razor charges $7/lot round-turn for FX majors
- **The backtest uses HALF the real commission cost** — backtest results are optimistically biased

### Swap Rate Comparison
- `Meta/swap_rates.md:10-17` has actual MT5-verified swap rates
- `core/cost_model.py:56-57` has hardcoded swap estimates (-0.5 bps long XAUUSD, +0.2 short)
- Verified XAUUSD swap: long = -77.35 points, short = +28.78 points (`Meta/swap_rates.md:10`)
- These are in different units (bps vs points) — not directly comparable without conversion
- **Swap rates are NOT wired into backtest engine** — Phase 7.1 assumed certain swap values but they are not reconciled against live data

### Broker-Side Restrictions
- **No scalping/HFT restrictions documented** in codebase
- **No min hold time** enforced
- **No news-time trading restrictions** in strategy code (though MLB has `news_blackout_minutes=60` at `strategies/mlb.py:77`)
- Triple-swap day convention: mentioned in `Meta/broker_verification_report.md:95` but "verify which day in your terminal" — **not confirmed**

---

## 11.3 Execution Quality Evidence

### ⚠️ NOT AVAILABLE — P2
- **No live/demo trade history with requote rate, signed slippage, or fill-time distribution**
- The `execution/` directory contains adapters but no execution quality statistics collector
- `risk/slippage_model.py` exists but no evidence it's been calibrated against live fills
- The `runtime/broker_connection.py` and `runtime/test_broker_connection.py` exist for connectivity testing but not for execution quality benchmarking

### News-Time Spread Widening
- **Not measured** in codebase
- MLB strategy (`strategies/mlb.py:77`) has a `news_blackout_minutes=60` but no mechanism to enforce spread-widening checks
- `monitoring/alert_rules.py:73-90` has `SpreadWideningAlert` but it checks against a static `normal_spread_pips=1.0` — not dynamically calibrated

---

## 11.4 Legal, Tax & Compliance (Thailand-based)

### Thai Regulatory Status
`Meta/broker_verification_report.md:116-156`:
- Thai SEC blocked spot crypto exchanges (Bybit, OKX, CoinEx, etc.) in June 2025
- CFD trading via ASIC-regulated broker is "a different regulatory lane"
- **Risk acknowledged**: "The regulatory landscape is evolving. Thai SEC filed additional cases against brokers routing through affiliated overseas platforms (Feb 2026)"
- Recommendation to consult a licensed advisor — **no evidence this has been done**

### ⚠️ GAP — P3:
- `research/thai_forex_landscape_report.md` exists but was not read in this audit
- **No tax reporting plan documented** in the codebase
- **No FX conversion risk assessment** for THB ↔ USD deposits/withdrawals
- No licensed advisor consultation confirmed

---

## 11.5 Counterparty Risk Table

| Risk | Probability | Impact | Mitigation Status |
|------|------------|--------|-------------------|
| Broker insolvency | Very Low (ASIC/FCA regulated) | HIGH — all capital at risk | ✅ Regulated entity with segregated funds |
| Server outage | Low-Medium | HIGH — cannot trade/close positions | ⚠️ No functional failover (see 11.6) |
| Broker halts specific symbol | Low | MEDIUM — open position trapped | ⚠️ No automated detection |
| Spread explosion (news/event) | Medium | MEDIUM — adverse fills | ⚠️ SpreadWideningAlert exists but not wired to trade gate |
| Broker changes margin requirements | Medium | HIGH — forced liquidation | ⚠️ No margin change monitoring |
| Account hacked/credentials leaked | Low-Medium | CRITICAL — total loss | **❌ P0 — plaintext credentials in repo** (see 11.6 and Phase 20) |
| Counterparty blocks withdrawals | Very Low | HIGH — trapped funds | ⚠️ No documented contingency |
| Regulatory shutdown (Thai SEC) | Low-Medium | HIGH — cannot access broker | ⚠️ Multi-broker planned but not functional |
| Deposit/withdrawal delays | Low | LOW | ⚠️ Not monitored |
| PEP/AML/KYC flag on account | Very Low | HIGH — frozen account | ⚠️ Not addressed |

---

## 11.6 Multi-Broker Skeleton-vs-Functional Audit (R19)

### Skeleton Only — P0

**`governance/multi_broker_policy.py:1-32`**: Contains exactly:
- `BrokerRequirements` dataclass with 8 boolean fields (all default True)
- `MultiBrokerPolicy` dataclass with `brokers: list` (default empty)
- `add_broker()` and `count()` — that's it

### Has _failover() any executable code path?
**NO.** There is no `_failover()` method anywhere in the codebase. There is no `BrokerManager` class. The notion of "multi-broker failover" exists only as:
1. A configuration field in `core/config.py:37-39`:
   ```python
   primary_broker: str = "ic_markets"
   fallback_broker_1: str = "pepperstone"
   fallback_broker_2: str = "xm"
   ```
   These are **never referenced** by any execution or connection logic.
2. The `MultiBrokerPolicy` class which is never instantiated in production code.

### BrokerRequirements fields populated with real data?
**NO.** All fields are hardcoded `True` defaults. `validate()` at `multi_broker_policy.py:16-21` checks that all fields are True — but since they default to True, this always passes. These are placeholders.

### Is `validate()` called from live path?
**NO.** `BrokerRequirements.validate()` is defined but never called from the trading loop, orchestrator, or startup sequence.

### ⚠️ CRITICAL — FALSE CLAIM DETECTED (R19):
The `Meta/broker_verification_report.md:154` says "Maintain accounts at 2+ brokers (Pepperstone + IC Markets or OANDA)" — this implies counterparty diversification exists or is imminent. **This is FALSE**: only one broker is configured, the multi-broker "policy" is an empty skeleton, and no functional failover mechanism exists. **Counterparty risk is NOT diversified.**

### ⚠️ CRITICAL: Plaintext credentials in repo
`Meta/pepperstone_creds.txt.backup` contains plaintext login (61547941) and password (Graxia-12345). While the file comment says "DO NOT commit this file to git," it EXISTS in the working directory. This is a credential exposure regardless of git tracking status.

---

## 11.7 Multi-Broker Completion Roadmap

### Minimal path from skeleton to functional failover:
1. Implement `BrokerManager` class with `_failover()` method
2. Connect `primary_broker`/`fallback_broker_1`/`fallback_broker_2` config fields to actual connection logic
3. Add health-check monitoring that triggers failover on: connection loss > N seconds, consecutive order failures, margin call
4. Populate `BrokerRequirements` per-broker from actual contract specs (not hardcoded True)
5. Call `BrokerRequirements.validate()` at startup for each configured broker
6. Test failover in demo environment before any live claims
7. Remove `Meta/pepperstone_creds.txt.backup` or move it to `~/.secrets/`

### Estimated effort: 2-4 weeks of development + 1 week demo testing
### Current status: 0% complete — pure placeholder scaffolding (R19)

---

## Top Findings (Phase 11)

| # | Severity | Finding |
|---|----------|---------|
| 1 | **P0** | Multi-broker failover is a skeleton — `_failover()` does not exist, `BrokerRequirements` fields are placeholder defaults, `validate()` never called from live path |
| 2 | **P0** | Plaintext credentials in `Meta/pepperstone_creds.txt.backup` — login + password exposed in working directory |
| 3 | **P1** | Backtest uses $3.5/lot commission vs real $7/lot (Pepperstone Razor) — 2× optimistic bias |
| 4 | **P1** | Codebase is inconsistent about broker identity: config says IC Markets, env example says Pepperstone, broker_profile says ICMarkets-Demo02 |
| 5 | **P2** | No execution quality evidence (requote rate, slippage, fill-time distribution) collected from demo/live trading |
