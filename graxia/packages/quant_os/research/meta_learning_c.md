# Direction C — Meta-Learning Ledger

**Purpose:** Track what Direction C (Volume-Price Divergence in Crypto) learns.

---

## 1. BTC Volume-Price Divergence — REJECTED (2026-07-13) — trial #2001

**What we did:** When BTC makes new 20-day high but volume < 80% of average → short (weak move). New low + low volume → long.

**What the data said:** p=0.5533, Sharpe -2.058, win rate 33.3%, 6 OOS trades.

**Why it failed:** Only 6 trades generated. The strategy is too selective. Most bars don't trigger the divergence condition. When it does trigger, it loses money (negative Sharpe).

**Implication:** Volume divergence on BTC daily is too rare to be tradeable.

---

## 2. ETH Volume Confirmation — REJECTED (2026-07-13) — trial #3002

**What we did:** When ETH price and volume both confirm (new 10-day high + volume > 80th percentile) → long.

**What the data said:** p=0.5914, Sharpe 0.815, win rate 60.7%, 28 OOS trades.

**Why it failed:** Interesting win rate (60.7%) but only 28 trades < 100 target, p=0.59 not significant. The confirmation condition is also too selective.

**Implication:** Volume confirmation on ETH daily may have something, but sample too small.

---

## 3. BTC-ETH Volume Divergence Spread — REJECTED (2026-07-13) — trial #2003

**What we did:** Cross-asset volume divergence — when BTC vol high + ETH vol low → long BTC (relative strength).

**What the data said:** p=0.1877, Sharpe 1.281, win rate 48.5%, 68 OOS trades. DSR passes (1.0). But 68 < 100 trades target. Underpowered.

**Why it failed:** Most promising result of Direction C (Sharpe 1.28, DSR passes). But 68 trades < 100 target, p=0.19 not significant. Underpowered.

**Hourly validation (2026-07-13):** Downloaded 17,468 hourly BTC/ETH candles (2 years). Best config: W=24h, T=0.2, H=24h → 646 trades, Sharpe 0.85, p=0.173. **Sharpe inflated by small sample** — converged from 1.28 (68 trades) to 0.85 (646 trades). Not significant at any config.

**Implication:** Volume divergence on BTC/ETH is not a real edge. The daily BEVS Sharpe of 1.28 was sample-size noise.

---

## 4. Consecutive Gate Failure Tracker (Direction C)

| Gate | Count | Last Failed | Threshold | Status |
|------|-------|-------------|-----------|--------|
| p-value | 3 | BEVS | 3 | **STOP TRIGGERED** |
| WFA OOS positive | 3 | BEVS | 3 | **STOP TRIGGERED** |
| WFE | 2 | BEVS | 3 | ok |
| DSR | 2 | BEVS | 3 | ok |
| Bootstrap CI | 3 | BEVS | 3 | **STOP TRIGGERED** |
| Min trades | 3 | BEVS | 3 | **STOP TRIGGERED** |

**⚠️ STOPPING RULE TRIGGERED:** 3 consecutive p-value failures (BTCVD, ETHVC, BEVS). Research should STOP per stopping rule.

---

## 5. Overall Conclusion (All Directions)

**11 hypotheses tested across 3 directions. 0 passed all gates.**

| Direction | Hypotheses | Best Result | Verdict |
|-----------|-----------|-------------|---------|
| A (XAUUSD technical) | 4 | p=0.244 (MRM) | ALL REJECTED |
| B (multi-instrument) | 4 | p=0.248 (BVC) | ALL REJECTED |
| C (crypto volume) | 3 | p=0.188 (BEVS) | ALL REJECTED |

**Edge is not accessible with current data, methodology, and instruments.**
