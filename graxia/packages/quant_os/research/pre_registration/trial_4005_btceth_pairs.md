# Pre-Registration — Trial 4005: BTC/ETH Pairs Trading (Direction K)

**Status:** FROZEN — 2026-08-06 (arms + params locked; no tuning after this point)
**Direction K** (`reports/stopping_rule_2026_08_06_direction_k.md`, ledger `research/trial_ledger_k.json`)

## Hypothesis

BTC/ETH is a structurally co-moving pair (return correlation 0.83 over 50k
joint H1 bars, 2020-2026). When the log-price ratio diverges from its rolling
mean by >= 2σ, mean reversion of the ratio produces net-of-cost profit —
classic statistical arbitrage, structurally different from every directional
mechanism tested so far (all REJECTED across directions A-J).

## Why this is structurally different

1. **Market-neutral**: long/short spread — not directional, survives regime
2. **High frequency**: H1 data (50k bars) — unlike weekly COT
3. **Same-sector pair**: crypto-crypto, high correlation (0.83), liquid
4. Costs: Binance spot taker fee 10 bps rt + spread — realistic for crypto

## Arms (FROZEN — strategy defaults)

| Arm | Strategy | Logic |
|-----|----------|-------|
| 4005a | `compute_pairs_mr_signal` | log-ratio z-score, entry 2.0, exit 0.5, lookback 60 |
| 4005b | `compute_pgm_pairs_signals` | Engle-Granger cointegration (p<0.05) + z-score, half-life, ATR stops |

## Method

- BTCUSD_H1 + ETHUSD_H1 (50k joint bars, 2020-06 → 2026-06)
- Ratio = log(BTC/ETH); spread z-score per arm config
- Backtest: long ratio (long BTC/short ETH) when z <= -2, short when z >= +2,
  exit at |z| <= 0.5; ATR stop for PGM arm
- Costs: Binance taker 10 bps rt (2 × 5 bps per leg, standard spot fee) +
  slippage 2 bps/leg = **~14 bps rt per pair trade**
- Gates: pooled DK t > 2.0 & mean > 0 → GO; t > 1.5 → MARGINAL; else REJECT
- Min trades >= 100 (H1 frequency — expect thousands)

## Stopping rule

Direction K budget 8 trials; stop at 3 consecutive fails / 3 months / 40 hours.

## Provenance

Stamped via registry_schema.stamp_trial_entry() (trial 4005, id DIRK-BTCETH-PAIRS).
Pre-registered BEFORE any backtest (F27).
