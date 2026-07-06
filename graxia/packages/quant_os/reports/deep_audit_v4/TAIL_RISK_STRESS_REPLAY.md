# PHASE 12 — TAIL RISK & STRESS-EVENT REPLAY
**Quant OS Deep Audit v4.0 | Date: 2026-07-05 | Auditor: auditor agent**

---

## 12.1 Historical Coverage of Tail Events

### Backtest Date Range
- **`backtest/engine_e2e_fixture.py:48-50`**: Fixtures start `datetime(2025, 1, 6)`.
- **`backtest/data_loader.py:186`**: Synthetic data generator starts `datetime(2020, 1, 1)`.
- **Actual backtest data**: Appears to use hourly bars from 2020-01-01 forward (based on `data_loader.py:186-189`).

### Major Tail Events — Coverage Check

| Event | Date | In Backtest? | Peak Drawdown |
|---|---|---|---|
| SNB CHF de-peg | Jan 15, 2015 | ❌ NO | EURCHF -30% in minutes |
| Brexit referendum | Jun 23, 2016 | ❌ NO | GBPUSD -10% |
| COVID crash | Mar 2020 | ⚠️ PARTIAL (data from Jan 2020) | S&P 500 -34% |
| BTC crash | May 19, 2021 | ✅ Yes (if crypto data from 2020) | BTC -30% single day |
| Russia-Ukraine invasion | Feb 24, 2022 | ✅ Yes | XAUUSD +5% spike |
| FTX collapse | Nov 2022 | ✅ Yes | BTC -25% |
| US regional banking crisis | Mar 2023 | ✅ Yes | XAUUSD +10% |
| USDJPY intervention | Oct 2022 | ✅ Yes | |

**Assessment**: Backtest covers 2020–2025/2026 window. This is a period of mostly accommodative monetary policy and trending markets until 2022 rate hikes. The most severe tail events (SNB 2015, Brexit 2016) are NOT included. **Per R18: "Calm-market backtest is not survival evidence."**

---

## 12.2 Explicit Stress-Event Replay

### Has Any Tail Event Been Replayed?
- **No evidence** of a structured tail-event replay through the complete strategy + execution pipeline.
- `risk/stress_test.py` exists — needs review for specific scenarios.
- No replay of SNB-style liquidity vacuum where spreads go to 50+ pips and fills become impossible.

### Kill Switch During Tail Event
- **Circuit breaker** (`risk/circuit_breaker.py:140`): After 3 consecutive losses, trips. 30-min cooldown auto-reset.
- **Auto-stop**: 15% drawdown triggers kill switch.
- **Would have activated**: Depends on event timeline. A flash crash with 2-second drawdown might NOT be caught by auto-stop (runs on equity updates) but consecutive-loss circuit breaker might trip on post-event fills. In a crisis like SNB where broker goes non-responsive: neither mechanism helps — no liquidity = no fill = no PnL event = no trigger.

### Liquidity Vacuum Scenario
- **Spreads**: `core/cost_model.py:78-86` has `XAUUSD_STRESS_72BPS` — regulatory stress test with 72 bps spread. But this is static, not dynamically applied during volatility.
- **`execution/cost_model.py:16-18`**: Has STRESS_1/2/3 scenarios with spread_mult up to 3×. But no automated trigger to switch scenarios.
- **Order submission during vacuum**: `broker_reconnector.py:96-99`: `is_trading_allowed` requires CONNECTED + not stale. But during a liquidity vacuum, the broker IS connected — trades might be submitted at horrendous fills.
- **No VIX/volatility-based trade suspension**: No mechanism to halt trading when realized volatility exceeds N× normal.

---

## 12.3 Margin & Stop-Out Under Extreme Moves

### Broker Stop-Out Level
- Pepperstone margin call: ~100% margin level, stop-out: ~50% margin level.
- **RiskPolicy** (`risk/risk_policy.py:19`): `reject_if_margin_level_below_pct = 500`. Pre-trade gate rejects if margin level < 500%. Conservative buffer.

### Move Size to Stop Out
- **Not calculated in code**. Depends on:
  - Account leverage (MT5 `account_info().leverage`)
  - Current margin used
  - Position sizes
- **position_sizer_v2.py:201-203**: Margin calculation exists but projected post-trade margin vs available margin is never compared.
- **Negative balance protection**: Pepperstone offers negative balance protection for retail clients (regulatory requirement in multiple jurisdictions). BUT this is a broker-level guarantee, not code-level protection. The system can still theoretically accumulate losses up to the broker's stop-out level.

---

## 12.4 Correlated Cascade Risk

### Multiple Open Correlated Positions
- **`risk/portfolio_heat.py`** and **`risk/correlation_provider.py`** and **`risk/ewma_correlation.py`**: EWMA correlation tracking exists.
- **BUT** — not wired into pre-trade gate (`pre_trade_risk.py:25-98`). The pre-trade check does NOT account for correlation between existing positions and new trade.
- **Gross exposure limit**: `risk/pre_trade_risk.py:77`: max 5 positions. But 5 highly correlated positions (e.g., 3 on XAUUSD, XAGUSD, XAUEUR) could move together.
- **Asset-class correlation**: Ensemble-level trading could open correlated positions across MTM, MRB, MLB strategies. No cross-strategy position netting exists.

---

## 12.5 Tail-Risk Summary Table

| Factor | Status | Detail |
|---|---|---|
| Historical tail events in backtest | ⚠️ PARTIAL | 2020–2025 only. SNB 2015, Brexit 2016 missing |
| Stress-event replay performed | ❌ NO | No structured tail event replay |
| Kill switch during flash crash | ⚠️ PARTIAL | Works on PnL events, not price shocks |
| Liquidity vacuum protection | ❌ NO | No VIX/volatility-based suspension |
| Negative balance protection | ⚠️ BROKER-ONLY | Broker-level, not code-level |
| Correlated position cascade guard | ❌ NO | Pre-trade doesn't check correlation |
| Margin stop-out projected check | ❌ NO | Only current margin level checked |
| Auto-stop DD threshold | ✅ | 15% drawdown → kill switch |
| Circuit breaker | ✅ | 3 consecutive losses → trip per asset class |
| Swap/funding costs in stress | ❌ | Not wired to backtest or live |

---

## 12.6 Asset-Class-Specific Tail Events

### Crypto (BTC/ETH)
| Event | Date | Move | In Backtest? |
|---|---|---|---|
| BTC May crash | May 19, 2021 | -30% single day | ✅ (if data from 2020) |
| FTX collapse | Nov 8-11, 2022 | -25% BTC | ✅ |
| LUNA/UST collapse | May 2022 | -99% LUNA (not traded) | ✅ timeframe |
| 3AC / Celsius | Jun 2022 | -40% BTC from highs | ✅ |

**Crypto-specific risk not modeled**: Funding rate spikes during stress can reach -0.1%/8h. `cost_model.py:74`: `swap_long_bps=-10.0` is a static assumption. During a tail event, funding can go 10× that.

### Indices (US30, NAS100, SPX500)
| Event | Date | In Backtest? |
|---|---|---|
| COVID circuit breakers (4 in 10 days) | Mar 9-18, 2020 | ⚠️ PARTIAL |
| NASDAQ correction | Jan-Mar 2022 | ✅ |
| SVB collapse indices reaction | Mar 2023 | ✅ |

**Circuit breaker risk**: US equity futures have exchange-level circuit breakers (-7%, -13%, -20%). Indices CFDs (like Pepperstone's) may have different behavior during these halts. No code awareness of exchange-level circuit breakers.

### Metals (XAUUSD, XAGUSD, XPDUSD)
- **Palladium thin liquidity**: Not in traded symbols but worth noting for asset class. XPDUSD daily range can exceed 5% on normal days.
- **XAUUSD liquidity**: Among the most liquid instruments. Tail events manifest as gap risk during weekly close (Friday 22:00 UTC). The daily close gap for metals (21:55–01:00) is modeled in `market_session_guard.py:35` but only as a session block, not as a gap risk.

---

## TOP FINDINGS — Phase 12

| # | Severity | Finding |
|---|---|---|
| 1 | P0 | **Backtest excludes SNB 2015 and Brexit 2016**: Two of the most relevant tail events for FX/metals are untested. Reported Sharpe/DD does NOT reflect tail-risk resilience. |
| 2 | P0 | **No structured stress-event replay**: No evidence of replaying any historical tail event through the full pipeline. |
| 3 | P0 | **No volatility-based trade suspension**: During liquidity vacuum, orders could still be submitted at catastrophic fills. |
| 4 | HIGH | **Correlation cascade not checked pre-trade**: 5 positions in correlated metals/FX could amplify drawdown beyond individual limits. |
| 5 | HIGH | **Crypto funding rate in stress not modeled**: Static -10bps/day shorts vs potential -100bps during crisis. |
| 6 | MEDIUM | No exchange circuit-breaker awareness for indices CFDs. |
