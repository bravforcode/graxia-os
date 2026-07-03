# GRAXIA-OS MEGA PLAN v3.0 — RESEARCH-VERIFIED EDITION
## XAUUSD M15 → TARGET: >$2,000/month, fastest responsible lot-scaling | Capital: $5,000
### Locked: 2026-06-26 | Broker: Pepperstone ECN Razor | Lot: 0.01→0.04+
### Supersedes v2.0. Every external claim in this version was checked against a live source in June 2026 (see §0.3 and the Appendix bibliography). Corrections to v2.0 are flagged inline with 🔧 **[v3 FIX]**.

---

## 0. EXECUTIVE SUMMARY — READ THIS FIRST

### 0.1 What you asked for, and what this document does about it

You asked for four things: (1) expand every section, (2) maximize profit, (3) go find the actual best data-quality tools and models from GitHub/research instead of guessing, (4) scale lot size to >$2,000/month as fast as the evidence allows. This version does all four — but "maximize profit" and "be more careful/rigorous than before" (your own words: ครบถ้วนและรอบคอบมากกว่าเดิม) pull in the same direction, not opposite ones. The single biggest cause of blown trading accounts is scaling size faster than the statistical evidence justifies. Every "aggressive" lever in this document is paired with the math that tells you exactly how much risk that lever adds, so "fast" and "reckless" don't get confused.

### 0.2 The honest version of the profit target

I'm not a financial advisor and this isn't financial advice — what follows is the arithmetic, not a promise. A few things worth sitting with before you read further:

- **Every "Monthly EV" number in this document (and in v2.0) is a hypothesis to be tested, not a measured result.** As of today you have zero corrected backtests, zero paper trades, and zero live trades on this system. The $0.20–$2,20/trade EV figures are placeholders used for *planning arithmetic* (how many trades, how much capital, how fast can size grow *if* the edge turns out to be real). Treat every dollar figure before §9 (Phase 0) as "if-then," not "will."
- **>$2,000/month on $5,000 is a >40%/month return target.** Compounded, that's >fifty-fold annually. No retail strategy sustains that without either (a) genuinely rare statistical edge, or (b) risk levels that will eventually produce a large drawdown or margin call. This document gives you the fastest path the *evidence* supports, gated by statistics (t-stat, CPCV, PBO) rather than by your P&L curve or your patience — which is exactly the discipline that prevents over-scaling.
- **A new §2.4 (Monte Carlo & Risk of Ruin) lets you see, before risking a single dollar, the probability that a "scale fast" ladder produces a >50% drawdown versus a "scale on stricter evidence" ladder.** You choose the ladder; the document just makes the trade-off visible instead of hidden.
- Retail CFD/FX trading on margin is high-risk; most retail accounts lose money over time (this is disclosed by every regulated broker, including Pepperstone, in their risk warnings). Nothing here changes that base rate — it only tries to make sure *you* are not adding unforced errors on top of it.

### 0.3 What changed since v2.0 (research findings)

I went through the GitHub repos, libraries, broker fee schedules, and methodology papers cited in v2.0 and verified each one against a live source (searched June 2026). Several materially change the plan:

| # | v2.0 said | v3.0 finding | Why it matters |
|---|-----------|-----------|----------------|
| F1 | `pip install smart-money-concepts` | 🔧 Real package name is **`smartmoneyconcepts`** (no hyphens), `from smartmoneyconcepts import smc`. Latest release v0.0.27, Apr 2026, still actively maintained by joshyattridge. | The v2.0 install command would have failed outright. |
| F2 | `pip install mlfinlab` as a free Tier-1 library | 🔧 **mlfinlab has been closed-source / commercial since ~2021** (Hudson & Thames). `pip install mlfinlab` no longer resolves on PyPI for the maintained version. | You cannot rely on this for free. Use the open-source reimplementation `mlfinpy`, or — better, since the functions you need (triple-barrier labeling, fractional differentiation) are short — implement them yourself (code in §11A). |
| F3 | NautilusTrader as a live MT5 execution validator (dual-engine §6) | 🔧 **NautilusTrader has no official MetaTrader5 adapter.** As of v1.228.0 (Jun 2026) its stable integrations are Interactive Brokers, Binance, Bybit, Coinbase, Deribit, dYdX v4, Hyperliquid, Kraken, OKX, Polymarket, Betfair, BitMEX — no FX/CFD MT5 venue. | The "dual-engine" architecture is redesigned in §6: NautilusTrader is used **offline, on historical Dukascopy bars only**, as a second, independent backtest engine to cross-check VectorBT results (different fill/slippage model = a real second opinion). **Live execution stays on the MetaTrader5 Python package talking directly to Pepperstone**, same as before. |
| F4 | `skfolio.CombinatorialPurgedCV(purged_size=embargo_bars)` | 🔧 The real API has **two separate parameters**: `purged_size` (removes overlap on both sides of the test fold) and `embargo_size` (removes the post-test window only, for serial correlation). v2.0 only set one. | Under-purging leaks information across folds, which is exactly Bug #3 you were trying to fix. Corrected code in §7. |
| F5 | Cost model: spread + flat commission, no overnight cost | 🔧 **No swap/overnight financing was modeled anywhere in v2.0.** Pepperstone charges a TomNext-based swap on any position held past the NY 5pm rollover, with a triple charge on one day of the week (verify which day in your account terminal — it varies by instrument and broker policy period). For metals, Pepperstone's Razor commission is **already embedded in the quoted spread**, not a separate $3.50/lot/side fee like FX pairs. | If your model ever holds a trade across rollover (including unintentionally, e.g., a position open at Friday close), you are missing a real cost. New **Bug #8** in §1, full cost model in §1 and §9. |
| F6 | `vectorbt` open-source, used as primary research engine | Confirmed real and still installable (`pip install vectorbt`, v1.0.0+), but **the open-source edition is now community-maintained only** — new features land in the paid VectorBT Pro. Fine for this project's needs (signal sweeps, portfolio stats), just don't expect new features. | No action needed, just set expectations. |
| F7 | HMM (hmmlearn) as the only regime detector | 🆕 **Statistical Jump Models (`pip install jumpmodels`)** — Nystrup/Kolm/Mulvey/Shu, 2020–2025 — are a published, actively-maintained, scikit-learn-style alternative designed specifically to fix HMM's two biggest weaknesses for trading: (a) regime flicker (HMM states can switch every few bars; JMs penalize switching directly, so regimes are more persistent — which matters a lot here because each regime switch reroutes your trade to a different specialist model with a different stop/target), and (b) sensitivity to non-Gaussian, fat-tailed financial returns. Sparse-JM also does feature selection automatically. Includes a `.predict_online()` method built for exactly this live-bar-by-bar use case. | Added as the **primary** regime detector in §11C/§8, with HMM kept as a secondary cross-check (if the two disagree more than X% of the time, that's itself a useful regime-uncertainty signal, see §11C). |
| F8 | CFTC COT data via manual ZIP download | 🆕 `pip install cot_reports` (NDelventhal) automates this, and the CFTC also exposes a documented Socrata REST API (`publicreporting.cftc.gov`) for direct queries with no file unzip step. | Less brittle pipeline, code in §11E. |
| F9 | Deflated Sharpe / PBO mentioned conceptually | 🆕 `pip install pypbo` implements Bailey & López de Prado's Probabilistic Sharpe Ratio, Minimum Track Record Length, Deflated Sharpe Ratio, and PBO directly. | New §7B gives you a number, not just a concept, for "how likely is it that this result is a fluke given how many configurations I tried." |
| F10 | Thai regulatory status not addressed | 🆕 Brief regulatory note added (§17.5). Sources disagree on some details (whether spot FX/CFD with an offshore broker falls under the Bank of Thailand's Exchange Control Act registration/cap regime, versus a more liberalized framing some broker-comparison sites use) — this is **not legal advice**; verify your own compliance directly with BOT/a licensed advisor, especially around the annual outbound-investment registration step some sources describe. | Avoids you operating on a confident-sounding but possibly wrong legal assumption. |

Everything else in v2.0's architecture (the bug fixes, the phase structure, the general direction) was sound and is kept, expanded, and in most sections rewritten for more depth below.

---

## 1. SYSTEM AUDIT v3 — ALL BUGS + NEW FINDINGS

### Bug #1 (CRITICAL): PnL multiplier hardcoded at 2350 — kept from v2.0, unchanged, still correct
**File:** `walk_forward.py:76`
**Impact:** ALL historical PnL figures off by ×(live_price/2350). At XAUUSD ~3340 today: understated by **1.42×**.

```python
# WRONG — current code:
raw_pnl_dollars = dir_mask * rets * 2350.0

# CORRECT — use actual bar close price array:
# test_close_prices: np.ndarray, same shape as rets
# 0.01 lot = 1 oz, so dollar PnL = price_change × 1 oz
raw_pnl_dollars = dir_mask * rets * test_close_prices

# HOW TO GET test_close_prices:
# In the WF loop, when you slice the test fold:
# test_close_prices = close_array[test_idx]   # shape: (n_test_bars,)
```

**Verify the fix is correct:**
```python
assert test_close_prices.shape == rets.shape, "Shape mismatch — wrong array passed"
assert test_close_prices.min() > 1000,        "Price sanity: XAUUSD should be >$1000"
assert test_close_prices.max() < 5000,        "Price sanity: XAUUSD should be <$5000"
```

---

### Bug #2: Cost constant stale, and incomplete (metals ≠ FX commission model) 🔧 [v3 FIX]
**File:** `walk_forward.py`

v2.0 treated XAUUSD like an FX pair: `spread + flat per-side commission`. Research finding: on Pepperstone Razor, **commission on metals (XAUUSD) is built into the quoted spread**, unlike the separate $3.50/lot/side commission charged on FX CFDs. Quoting both a spread *and* an extra commission for gold double-counts a cost that isn't structured that way for this instrument.

```python
# WRONG (v2.0, calibrated at 2350, off by price ratio, AND assumes FX-style separate commission):
COST_PER_TRADE = 0.345   # then later "corrected" to 0.18 — still wrong structurally

# CORRECT v3 — for XAUUSD on Razor, cost = round-trip spread only (commission already inside it).
# Pull this LIVE from your terminal every session rather than hardcoding it — gold spreads on Razor
# move with session liquidity (tightest London/NY overlap, widest Asian session + any NFP/CPI/FOMC window).
import MetaTrader5 as mt5

def get_live_round_trip_cost(symbol: str = "XAUUSD") -> float:
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    spread_dollars = tick.ask - tick.bid          # already in price units for XAUUSD
    return spread_dollars                          # round-trip cost = pay the spread once per entry

# For BACKTESTS where you don't have live ticks, use the avg_spread column from your Dukascopy
# aggregation (see §10) — NOT a single hardcoded constant. Recalibrate the backtest constant
# quarterly against your paper/live spread log, and segment it by session (Asian vs London vs NY)
# since gold spread can be 2-3x wider in the Asian session on a Razor account.
COST_PER_TRADE_BY_SESSION = {
    "asian":   0.28,   # placeholder — replace with your own measured avg_spread by session
    "london":  0.14,
    "ny":      0.15,
    "overlap": 0.12,
}
```

**🔧 [v3 FIX — NEW Bug #8 below] this cost model is still incomplete without swap.**

---

### Bug #3: Data leakage — train_acc = 100%
**Root cause:** Triple-barrier labels look forward ≥12 bars. Standard CV splits contaminate validation folds within that window.

**Fix:** Combinatorial Purged CV (CPCV) with **both** `purged_size` and `embargo_size` set (🔧 v2.0 only set one — see §7 for the corrected call). This replaces PurgedKFold entirely in v3.0.

---

### Bug #4: Paper trade not running
**Fix:** Start paper trade automation after Day 1 bug fixes. See §9.

---

### Bug #5: Walk-Forward tests only ONE backtest path
**Fix:** Replace WF with CPCV — generates 15+ independent backtest paths, reports a *distribution* of Sharpe ratios, and (🆕 v3) feeds that distribution into a Probability-of-Backtest-Overfitting (PBO) and Deflated Sharpe Ratio calculation (§7B) so "looks great" and "statistically is great" stop being the same question by accident.

---

### Bug #6: No regime conditioning
**Fix (🔧 v3 upgrade):** Primary regime detector is now a **Statistical/Sparse Jump Model** (`jumpmodels`), not HMM — see §8 and §11C for why and the code. HMM is retained as a secondary cross-check model.

---

### Bug #7: No SMC microstructure features
**Fix (🔧 v3 correction):** `pip install smartmoneyconcepts` (not `smart-money-concepts`) — see §11A.

---

### Bug #8 (NEW, v3): No swap / overnight financing cost modeled anywhere
**Impact:** Pepperstone charges a TomNext-derived swap for any position held through the daily rollover (5pm New York time / 23:59 platform server time), with **one day of the week carrying a triple charge** to account for weekend settlement (confirm which day applies in your live account terminal — this can shift between brokers and review periods, so don't hardcode an assumption here). An M15 strategy is *mostly* intraday, but:
- A trade opened late in the NY session can roll into the next day's swap without the strategy "intending" to hold overnight.
- Friday-close positions that aren't force-flattened will sit through the weekend gap *and* may attract the multi-day weekend swap.
- If Phase 4+ ever lets winners run (the TRENDING regime config in §12 uses a wider 1.5–2× ATR stop/target — that can keep a position open for hours, plausibly across rollover).

**Fix — two parts:**

1. **Pre-registration decision (do this explicitly, in writing, before Phase 0):** Will GRAXIA-OS be a strict "flatten before rollover" intraday system, or will it allow overnight holds? This is a real design choice with real cost/behavior implications, not a detail.
2. **If overnight holds are allowed, model the cost:**

```python
# core/risk/swap_cost.py
import MetaTrader5 as mt5
from datetime import datetime, timezone

def get_live_swap_rates(symbol: str = "XAUUSD") -> dict:
    """
    Pull live long/short swap rates (in points, broker-quoted) directly from the
    terminal rather than hardcoding a number that will go stale. Verify in your
    account which calendar day carries the triple charge — check the symbol
    specification / contract details panel in MT5, do not assume Wednesday.
    """
    info = mt5.symbol_info(symbol)
    return {
        "swap_long":  info.swap_long,    # points/day, can be negative
        "swap_short": info.swap_short,
        "swap_mode":  info.swap_mode,    # 0 = points, 1 = % per annum, 2 = currency, etc. — check enum
    }

def estimate_overnight_cost(direction: str, lot: float, nights_held: int,
                              triple_swap_weekday: int, swap_rates: dict,
                              point_value_per_lot: float = 1.0) -> float:
    """
    point_value_per_lot for XAUUSD at 0.01 lot ≈ $0.01 per point (1 oz × $0.01/point) —
    VERIFY against your broker's contract specification, do not assume.
    triple_swap_weekday: 0=Mon..6=Sun, set from your account's symbol spec, not guessed.
    """
    rate = swap_rates["swap_long"] if direction == "BUY" else swap_rates["swap_short"]
    multiplier = 3 if nights_held == 1 and datetime.now(timezone.utc).weekday() == triple_swap_weekday else 1
    return rate * point_value_per_lot * lot * nights_held * multiplier
```

3. **Pandera/backtest integration:** add a `swap_cost` column to every backtest trade row (default 0 if flattened intraday) so Phase 0–1 baselines and live results are cost-comparable.

---

### Bug #9 (NEW, v3): NautilusTrader has no MT5 adapter — the v2.0 "dual-engine" design needs redrawing
See Finding F3 in §0.3 and the corrected architecture in §6.

---

### NEW: No VPS → Live trading at risk (kept from v2.0, expanded in §4)
**Fix:** Set up Windows VPS before going live, with a **second, cold-standby VPS** in a different provider/datacenter as a failover (new in v3, see §4D) — a single VPS is still a single point of failure for real-money trading.

---

## 2. CAPITAL MATH & SCALING TO >$2,000/MONTH — WITH RISK MADE VISIBLE

### 2.1 Lot Size ↔ Dollar P&L (unchanged mechanics, kept from v2.0)

```
At XAUUSD ~$3,340 (current, Jun 2026):

0.01 lot = 1 oz   → $1 price move = $1.00 P&L
0.02 lot = 2 oz   → $1 price move = $2.00 P&L
0.04 lot = 4 oz   → $1 price move = $4.00 P&L

B2 stop at $6.30 loss (price moved $6.30 against position)
```

### 2.2 Monthly EV — illustrative scenario table (NOT a forecast)

🔧 **[v3 framing change]** — these are the same arithmetic placeholders as v2.0, relabeled honestly. Nothing below has been measured yet. Treat as "if EV/trade and trade count land here, monthly P&L lands here," full stop.

| Config | EV/trade (hypothesis) | Trades/month | Monthly EV (arithmetic only) | Max DD (1R-based estimate) |
|--------|----------|-------------|-----------|--------|
| 0.01 lot, baseline | $1.50 | 540 | $810 | -$630 |
| 0.01 lot, Phase 4 complete | $2.20 | 540 | $1,188 | -$630 |
| 0.02 lot, Gate 6 passed | $2.20 | 540 | $2,376 | -$1,260 |
| 0.03 lot, Gate 6 again | $2.20 | 540 | $3,564 | -$1,890 |
| 0.04 lot, capital grown | $2.20 | 540 | $4,752 | -$2,520 |

These DD figures are **single-bad-stretch** estimates (a run of losses at one fixed lot), not the *worst case across the whole scaling path*. §2.4 fixes that gap with an actual simulation.

### 2.3 Two scaling ladders — you choose, the document shows you the trade-off

You said you want the fastest path to >$2,000/month. Here are two versions of "fast." The difference between them is entirely in how much statistical evidence is required before each lot increase — nothing else changes.

**Ladder A — "Fast" (your stated preference): scale the moment each gate's *minimum* threshold is crossed.**

| Month | Lot | Gate | Expected (arithmetic) | Hard Stop |
|-------|-----|------|---------|-----------|
| 1 (Jul) | 0.01 paper | B2 pre-reg pass | Validate | $0 real |
| 2 (Aug) | 0.01 LIVE | Paper PASS Jul 23 | $810–$1,188 | -$630 |
| 3 (Sep) | 0.01 LIVE | Building 1k+ trades | $810–$1,188 | -$630 |
| 4 (Oct) | 0.02 LIVE | Gate 6: t-stat≥2.0, ≥1k trades | $1,620–$2,376 | -$1,260 |
| 5 (Nov) | 0.02 LIVE | Maintain | $1,620–$2,376 | -$1,260 |
| 6 (Dec) | 0.03 LIVE | Gate 6 again at 0.02 tier | $2,430–$3,564 | -$1,890 |

**Ladder B — "Fast, with a margin of safety": same calendar, but each step also requires the Monte Carlo risk-of-ruin check in §2.4 to clear before the lot increase executes — not just t-stat ≥ 2.0 on a single point estimate.**

The calendar dates don't change between A and B. What changes is that B can *delay* a step if the simulation says the edge isn't yet stable enough to support the next lot tier — i.e., B is "fast until the data says don't," rather than "fast on a fixed calendar regardless." Given you explicitly want maximum speed, **Ladder A is the default below**, but §2.4's check is still run every time, logged, and shown to you — if it ever flags a >25% probability of breaching the kill-switch balance ($4,500) within the next 90 days at the new lot size, that is reported as a hard blocker even on Ladder A, because that specific failure mode (ruin) is not a "slower vs faster" trade-off, it's account-ending.

**Compound Projection (reinvest profits, no withdrawals) — same as v2.0, kept as the headline number you're optimizing for:**

```
Month 1: $5,000 base, +$1,000 (0.01 lot) → $6,000
Month 2: $6,000 base, +$1,100               → $7,100
Month 3: $7,100 base, +$1,188               → $8,288
Month 4: $8,288 base, 0.02 lot, +$2,200     → $10,488
Month 5: $10,488 base, +$2,300              → $12,788
Month 6: $12,788 base, 0.03 lot, +$3,500   → $16,288
```

At Month 6: **>$3,500/month run rate**, capital $16,288 — *if* the EV/trade hypotheses above hold up under live conditions. §2.4 tells you how often, in simulation, they don't.

### 2.4 🆕 Monte Carlo Simulation & Risk of Ruin (this section did not exist in v2.0)

This is the single most important addition for someone optimizing for speed: it converts "scale as fast as possible" from a vibe into a number you can actually act on. The idea — résample your own (eventual) trade-level P&L distribution thousands of times in random order and with random subsets, and see the *spread* of outcomes, not just the average.

```python
# core/risk/monte_carlo.py
"""
Run this BEFORE every lot increase (Gate 5, 6, 6b...), using the most recent
≥300 trades' actual P&L distribution (paper or live — whichever the gate is checking).
Never use the hypothetical EV/trade tables in §2.2 as simulation input once you
have real trades; those tables are for pre-launch arithmetic only.
"""
import numpy as np

def bootstrap_equity_paths(
    trade_pnls: np.ndarray,      # actual historical/paper/live per-trade net P&L, $
    n_sims: int = 10_000,
    n_trades_forward: int = 540,   # ~1 month at M15 cadence per v2.0's trade-count assumption
    starting_balance: float = 5000.0,
    kill_switch_balance: float = 4500.0,
    lot_multiplier: float = 1.0,    # set >1.0 to simulate the NEXT lot tier's P&L scaling
) -> dict:
    n = len(trade_pnls)
    paths = np.zeros((n_sims, n_trades_forward))
    for i in range(n_sims):
        sampled = np.random.choice(trade_pnls, size=n_trades_forward, replace=True) * lot_multiplier
        paths[i] = starting_balance + np.cumsum(sampled)

    ruin_mask = (paths <= kill_switch_balance).any(axis=1)
    max_dd_pct = np.array([
        ((np.maximum.accumulate(p) - p) / np.maximum.accumulate(p)).max()
        for p in paths
    ])

    return {
        "prob_ruin":            ruin_mask.mean(),                  # P(hit kill-switch balance within horizon)
        "median_ending_balance": np.median(paths[:, -1]),
        "p5_ending_balance":     np.percentile(paths[:, -1], 5),    # bad-case
        "p95_ending_balance":    np.percentile(paths[:, -1], 95),   # good-case
        "median_max_dd_pct":     np.median(max_dd_pct),
        "p95_max_dd_pct":        np.percentile(max_dd_pct, 95),     # 1-in-20 bad month
    }

# DECISION RULE tied into Gate 6 (see §16):
# If prob_ruin > 0.05 at the CURRENT lot → stop trading, full diagnostic, do not scale.
# If prob_ruin > 0.02 at the NEXT lot tier (lot_multiplier=2.0 etc.) → do not take this lot increase yet,
#   even if t-stat ≥ 2.0 and trade count ≥ 1000. Re-check after 200 more trades.
# These thresholds are a starting point, not a law of nature — set them explicitly in your
# pre-registration (§15) BEFORE you see the first Monte Carlo output, for the same p-hacking
# reason you pre-register everything else.
```

Why this matters for *your* stated goal specifically: a system that passes Gate 6's t-stat/trade-count bar can still have, say, a 1-in-8 chance of a 40%+ drawdown in the next month at the new lot size, purely from variance — that's not visible from a single t-stat. Running this simulation costs you nothing but compute time and tells you exactly how much "fast" is costing you in tail risk, so you can decide with full information rather than finding out the hard way.

## 3. GITHUB REPOS & LIBRARIES — RESEARCH-VERIFIED (June 2026)

Every entry below was checked against PyPI/GitHub directly this session. "Verified" = package name, install command, and maintenance status confirmed live. Do not just clone-and-run any of these — extract the pattern, adapt, integrate into GRAXIA-OS's own architecture, as v2.0 already correctly advised.

### Tier 1: Directly Incorporate (High Signal, all verified)

| Repo / Package | What to Take | Install | Verification note |
|------|-------------|---------|---|
| `joshyattridge/smartmoneyconcepts` | Order Block, FVG, BOS, CHoCH, liquidity sweep, swing H/L detection | 🔧 `pip install smartmoneyconcepts` (corrected name) | v0.0.27 released Apr 2026, actively maintained, MIT-style license, "for educational purposes — do not use as sole decision maker" per the author's own README. |
| `Yizhan-Oliver-Shu/jump-models` | 🆕 Statistical Jump Model (JM), Continuous JM (CJM), Sparse JM (SJM) for regime detection — see §8 | `pip install jumpmodels` | Published research (Nystrup 2020, Aydınhan/Kolm/Mulvey/Shu 2024–25), scikit-learn-style `.fit()/.predict()/.predict_proba()`, plus `.predict_online()` for exactly this live-bot use case. |
| `hmmlearn` (kept, demoted to secondary detector) | `GaussianHMM` for a cross-check regime signal | `pip install hmmlearn` | Stable, widely used; known weaknesses (regime flicker, Gaussian-emission mismatch with fat-tailed FX/gold returns) are exactly what the JM addition in F7 is meant to offset. |
| `skfolio` | `CombinatorialPurgedCV` — production-ready, 🔧 correct call needs both `purged_size` and `embargo_size` | `pip install skfolio` | v0.10.x on PyPI, actively developed, originally a portfolio-optimization library but the CV splitter is general-purpose (works on any indexable `X`). |
| `esvhd/pypbo` | 🆕 Probability of Backtest Overfitting, Probabilistic Sharpe Ratio, Minimum Track Record Length, Deflated Sharpe Ratio — direct implementations of Bailey & López de Prado's methodology | `pip install pypbo` (or `pip install git+https://github.com/esvhd/pypbo` if not on PyPI in your environment — verify at install time) | Implements the exact statistics referenced conceptually in v2.0 §7; see §7B. |
| `NDelventhal/cot_reports` | Automated CFTC Commitment-of-Traders fetch, no manual ZIP handling | `pip install cot_reports` | MIT license, supports Legacy/Disaggregated/TFF report types; CFTC also exposes a Socrata REST API directly if you prefer to skip the library (`publicreporting.cftc.gov`). |
| `0xagarg/xau-ai-trading-bot` | 14-filter entry system, HMM integration patterns | Manual (study architecture) | Kept from v2.0 as a reference architecture, not a dependency. |

### Tier 2: Study Architecture (Reference, kept from v2.0)

| Repo | What to Learn |
|------|--------------|
| `zero-was-here/tradingbot` | 140+ feature list for DRL; PPO/Dreamer patterns |
| `ilahuerta-IA/backtrader-pullback-window-xauusd` | 4-phase state machine (WR 55.43%, DD 5.81%) — note this is a single reported backtest result, not a validated edge; treat the same way you'd treat your own un-pre-registered backtest |
| `JonusNattapong/Reinforcement-Learning-for-Gold-Trading` | PPO on XAUUSD M15 2004–2025 (Phase 6+ optional) |
| `CameronScarpati/lob-regime-scanner` | 30+ microstructure features for HMM/JM input |

### 🔧 Corrected / Removed from Tier 1

| Repo / Package | v2.0 status | v3.0 correction |
|---|---|---|
| `mlfinlab` | "Tier 1, `pip install mlfinlab`" | **Removed from Tier 1.** Closed-source/commercial since ~2021; `pip install mlfinlab` fails for the maintained version. If you specifically want the convenience functions, the open-source reimplementation `mlfinpy` (`pip install mlfinpy`) exists but verify its maturity before depending on it for anything load-bearing. Triple-barrier labeling and fractional differentiation are short enough to implement directly — see §11A code below, written from the published methodology rather than imported from a closed package. |
| `nautilus_trader` for live MT5 | "production validation" implying live bridging | **Kept, but scope corrected.** No MT5 adapter exists. Use it strictly as a second, independent *backtest* engine against your own historical Dukascopy Parquet bars (different fill/slippage assumptions than VectorBT = useful disagreement signal), not for live order routing. See §6. |

### Key Libraries to Add — verified install commands

```bash
# Data validation
pip install pandera deepchecks --break-system-packages

# SMC features — CORRECTED package name
pip install smartmoneyconcepts --break-system-packages

# Regime detection — PRIMARY (jump models) + SECONDARY (HMM)
pip install jumpmodels --break-system-packages
pip install hmmlearn --break-system-packages

# CPCV (Combinatorial Purged CV)
pip install skfolio --break-system-packages

# Backtest-overfitting statistics (Deflated Sharpe / PBO) — NEW in v3
pip install pypbo --break-system-packages

# COT report automation — NEW in v3 (replaces manual ZIP download)
pip install cot_reports --break-system-packages

# Advanced financial ML building blocks — mlfinlab is NOT free; implement
# triple-barrier + frac-diff yourself (short functions, code in §11A), or:
pip install mlfinpy --break-system-packages   # community reimplementation — vet before depending on it

# Fast backtesting (research phase) — confirmed working, community-maintained edition
pip install vectorbt --break-system-packages

# Production-grade backtest cross-check (NOT live execution — see §6)
pip install nautilus_trader --break-system-packages

# Fractional differentiation (stationarity)
pip install fracdiff --break-system-packages

# ADWIN drift detection
pip install river --break-system-packages
```

## 4. INFRASTRUCTURE: VPS + MONITORING + REDUNDANCY (CRITICAL — DO FIRST)

**This is the most important missing piece.** Live trading cannot run 24/7 on a home PC, and — new in v3 — a *single* VPS is still a single point of failure once real money is on the line.

### 4A: VPS Selection

For XAUUSD M15 (NOT HFT, NOT tick-sensitive), latency of 15–30ms is fine.

**Primary:** Contabo Windows VPS, London (LD4) datacenter — Pepperstone UK servers are in the same metro area, so latency stays low. Contabo's published entry pricing moves around (recent listings show plans from roughly €4.50–5/month for Linux base specs, with the Windows Server license added on top) — **verify the current quote at checkout rather than budgeting off this document**, since hosting prices are not stable over a 6-month planning horizon.

**🆕 4D — Secondary/failover VPS (did not exist in v2.0):** A second, smaller VPS from a *different* provider (e.g., Hyonix, or Contabo's Singapore/Germany location instead of London) running the same codebase in a cold-standby state. It does not place trades while the primary is healthy — it only takes over if the health-check watchdog (§4C) reports the primary as dead for longer than a defined threshold (e.g., 20 minutes / >1 missed M15 bar with no heartbeat). This adds maybe $5–10/month and removes "my VPS provider had an outage" as a way to lose money you didn't intend to risk. For a $5,000 account this is a genuinely cheap insurance policy relative to the downside of an un-managed open position during a VPS outage.

**Setup steps (Day 1, ~2 hours for primary, repeat the same checklist for the standby once primary is stable):**
```
1. Sign up for VPS provider → select Windows → London location (or your broker's nearest hub)
2. RDP into VPS (Windows Remote Desktop)
3. Download MT5 from Pepperstone → install → connect demo account first, live only after Phase 0-4
4. Copy Python environment from local machine:
   - Install Python 3.10+ on VPS
   - pip install -r requirements.txt
5. Clone repo to C:\graxia-os (use a deploy key, not your personal GitHub password)
6. Configure webhook.py to run on Windows startup
7. Repeat steps 1-6 on the standby VPS, but leave it in "watch only, do not place orders" mode
```

**Windows Task Scheduler (auto-start bot):**
```powershell
# In Task Scheduler → Create Basic Task:
# Name: GRAXIA-OS Bot
# Trigger: At startup
# Action: Start program
# Program: C:\Python310\python.exe
# Arguments: C:\graxia-os\webhook.py --live
# Start in: C:\graxia-os
```

---

### 4B: Telegram Alerting (kept from v2.0, unchanged — this design was already solid)

```python
# core/telegram_notify.py
import requests

TELEGRAM_TOKEN  = "YOUR_BOT_TOKEN"   # from @BotFather
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"    # from @userinfobot

class TelegramNotifier:
    def __init__(self, token: str = TELEGRAM_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token   = token
        self.chat_id = chat_id
        self.base    = f"https://api.telegram.org/bot{token}"

    def send(self, msg: str) -> bool:
        try:
            r = requests.post(
                f"{self.base}/sendMessage",
                json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=5
            )
            return r.status_code == 200
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

    def trade_opened(self, direction: str, entry: float, sl: float, tp: float,
                     confidence: float, lot: float, regime: str):
        emoji = "🟢 LONG" if direction == "BUY" else "🔴 SHORT"
        self.send(
            f"*GRAXIA-OS | {emoji}*\n"
            f"Entry: `{entry:.2f}` | Lot: `{lot}` | Regime: `{regime}`\n"
            f"SL: `{sl:.2f}` | TP: `{tp:.2f}`\n"
            f"Confidence: `{confidence:.3f}`"
        )

    def trade_closed(self, direction: str, pnl_net: float, reason: str,
                     daily_pnl: float, monthly_pnl: float, swap_paid: float = 0.0):
        emoji = "💚" if pnl_net > 0 else "❤️"
        self.send(
            f"{emoji} *CLOSED | {reason}*\n"
            f"P&L: `${pnl_net:+.2f}`" + (f" (incl. swap ${swap_paid:+.2f})" if swap_paid else "") + "\n"
            f"Daily: `${daily_pnl:+.2f}` | Monthly: `${monthly_pnl:+.2f}`"
        )

    def risk_alert(self, reason: str):
        self.send(f"⚠️ *RISK ALERT*\n{reason}")

    def heartbeat(self, trades_today: int, win_rate_7d: float, balance: float, prob_ruin_at_current_lot: float = None):
        msg = (
            f"💓 *Daily Heartbeat*\n"
            f"Trades today: `{trades_today}`\n"
            f"WR 7d: `{win_rate_7d:.1%}`\n"
            f"Balance: `${balance:,.2f}`"
        )
        if prob_ruin_at_current_lot is not None:
            msg += f"\nMonte Carlo P(ruin), current lot: `{prob_ruin_at_current_lot:.2%}`"
        self.send(msg)

    def failover_triggered(self, reason: str):
        self.send(f"🚨 *FAILOVER* — standby VPS is taking over.\nReason: {reason}\nVerify open positions manually NOW.")

# Usage: call notifier.heartbeat() daily at 00:05 UTC via scheduler
```

---

### 4C: Health Check + Failover (🔧 expanded from v2.0's single-VPS restart-only design)

```python
# monitoring/health_check.py
"""
Problem: webhook.py can silently die (exception, MT5 disconnect) without notice.
v2.0 fix: heartbeat file, watchdog restarts the SAME process on the SAME VPS.
v3.0 fix: watchdog also notifies the STANDBY VPS to take over if the primary
stays dead past a hard threshold — a local restart can't help if the VPS itself,
not just the python process, is the thing that's down.
"""
import time, pathlib, subprocess, sys, requests
from datetime import datetime, timezone

HEARTBEAT_FILE = pathlib.Path("data/heartbeat.txt")
MAX_STALE_SECONDS_LOCAL_RESTART = 900    # 15 min — try local restart first
MAX_STALE_SECONDS_FAILOVER      = 1800   # 30 min — escalate to standby VPS

def update_heartbeat():
    """Call this inside webhook.py main loop at start of each bar."""
    HEARTBEAT_FILE.write_text(datetime.now(timezone.utc).isoformat())

def trigger_standby_takeover(standby_webhook_url: str, notifier):
    """
    standby_webhook_url: a small always-on listener on the standby VPS (separate
    lightweight process) that flips it from watch-only to active on receiving this call.
    Use a shared secret / IP allowlist — this endpoint can place real trades.
    """
    try:
        requests.post(standby_webhook_url, json={"action": "activate"}, timeout=10)
        notifier.failover_triggered("Primary VPS heartbeat stale > 30min")
    except Exception as e:
        notifier.risk_alert(f"FAILOVER CALL FAILED: {e} — standby may not have activated, check manually")

def watchdog_loop(standby_webhook_url: str):
    notifier = TelegramNotifier()
    failover_sent = False
    while True:
        time.sleep(300)   # check every 5 min
        if HEARTBEAT_FILE.exists():
            last = datetime.fromisoformat(HEARTBEAT_FILE.read_text())
            age  = (datetime.now(timezone.utc) - last).total_seconds()
            if MAX_STALE_SECONDS_LOCAL_RESTART < age <= MAX_STALE_SECONDS_FAILOVER:
                notifier.risk_alert(f"Bot heartbeat stale {age:.0f}s — attempting local RESTART")
                subprocess.Popen([sys.executable, "webhook.py", "--live"])
            elif age > MAX_STALE_SECONDS_FAILOVER and not failover_sent:
                trigger_standby_takeover(standby_webhook_url, notifier)
                failover_sent = True
        else:
            notifier.risk_alert("No heartbeat file — bot never started!")
```

## 5. DATA QUALITY PIPELINE v3

### 5A: Pandera Schema — OHLCV Validation (kept from v2.0, unchanged — already solid)

```python
# core/schemas.py
import pandera as pa
from pandera import Column, Check, DataFrameSchema
import pandas as pd

XAUUSD_M15_SCHEMA = DataFrameSchema(
    columns={
        "open":       Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "high":       Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "low":        Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "close":      Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "volume":     Column(float, Check.greater_than_or_equal_to(0)),
        "avg_spread": Column(float, [Check.greater_than_or_equal_to(0), Check.less_than(5.0)], nullable=True),
    },
    checks=[
        Check(lambda df: (df["high"] >= df["low"]).all(),   error="high < low detected"),
        Check(lambda df: (df["high"] >= df["open"]).all(),  error="high < open detected"),
        Check(lambda df: (df["high"] >= df["close"]).all(), error="high < close detected"),
        Check(lambda df: (df["low"] <= df["open"]).all(),   error="low > open detected"),
        Check(lambda df: (df["low"] <= df["close"]).all(),  error="low > close detected"),
        Check(lambda df: (df["close"].pct_change().abs() < 0.05).all(),
              error="Price jump >5% detected — check data integrity"),
    ],
    index=pa.Index(pa.DateTime, name="timestamp"),
    coerce=True,
)

def validate_ohlcv(df: pd.DataFrame, source: str = "unknown") -> pd.DataFrame:
    try:
        validated = XAUUSD_M15_SCHEMA.validate(df)
        print(f"✅ OHLCV validation passed: {len(validated):,} bars from {source}")
        return validated
    except pa.errors.SchemaError as e:
        print(f"❌ Schema validation FAILED [{source}]: {e}")
        raise
```

---

### 5B: Dukascopy M15 Integrity Check (kept from v2.0, expanded)

```python
# scripts/verify_m15.py  — runs AFTER aggregate_ticks_to_m15.py
import pandas as pd
import numpy as np
from core.schemas import validate_ohlcv

def full_integrity_check(path: str) -> dict:
    b = pd.read_parquet(path)
    b.index = pd.to_datetime(b.index)

    validate_ohlcv(b, source=path)

    expected_freq = pd.Timedelta("15min")
    diffs = b.index.to_series().diff().dropna()
    long_gaps = diffs[diffs > expected_freq * 4]
    weekend_gaps = diffs[diffs > pd.Timedelta("2 days")]

    null_pct = b.isnull().mean()
    close_rets = b["close"].pct_change().dropna()
    skewness   = close_rets.skew()
    kurtosis   = close_rets.kurtosis()
    vol_bar_corr = b["volume"].corr(b["high"] - b["low"])

    report = {
        "total_bars":        len(b),
        "date_range":        f"{b.index[0]} → {b.index[-1]}",
        "null_pct_max":      null_pct.max(),
        "non_weekend_gaps":  len(long_gaps) - len(weekend_gaps),
        "price_jump_max":    close_rets.abs().max(),
        "n_jumps_gt_2pct":   (close_rets.abs() > 0.02).sum(),
        "return_skewness":   skewness,
        "return_kurtosis":   kurtosis,
        "vol_bar_corr":      vol_bar_corr,
        "avg_spread_usd":    b.get("avg_spread", pd.Series([0])).mean(),
    }

    print("\n=== DUKASCOPY M15 INTEGRITY REPORT ===")
    for k, v in report.items():
        print(f"  {k:<28} {v}")

    assert report["total_bars"] >= 260_000, f"Expected ≥260k bars for 10yr M15. Got {report['total_bars']:,}"
    assert report["null_pct_max"] < 0.005, f"Too many nulls: {report['null_pct_max']:.3%}"
    assert report["price_jump_max"] < 0.05, f"Price jump too large: {report['price_jump_max']:.3%}"
    assert report["non_weekend_gaps"] < 100, f"Too many non-weekend gaps: {report['non_weekend_gaps']}"

    print("\n✅ ALL INTEGRITY CHECKS PASSED")
    return report
```

---

### 5C 🆕: Cross-Source Reconciliation — Dukascopy vs. your live MT5 broker feed (did not exist in v2.0)

A real and common failure mode that v2.0 didn't cover: your *training* data (Dukascopy, aggregated from a different liquidity pool) and your *live execution* data (Pepperstone's own MT5 feed) are not guaranteed to be the same prices at the same timestamp. Gold is OTC, multi-source, and different brokers/venues can show small but non-trivial discrepancies — particularly around news spikes, where one feed might show a brief one-bar spike that the other doesn't. A model trained on Dukascopy bars and deployed on Pepperstone ticks is implicitly assuming these two are interchangeable; that assumption should be tested, not assumed.

```python
# scripts/reconcile_data_sources.py
"""
Run this once after Phase 2 (M15 aggregation) and again periodically during paper
trading: pull the same calendar window from BOTH Dukascopy (historical) and a fresh
MT5 pull from Pepperstone (rates_range / copy_rates_from), and compare.
"""
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

def fetch_pepperstone_m15(symbol: str, start, end) -> pd.DataFrame:
    mt5.initialize()
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start, end)
    mt5.shutdown()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time")[["open", "high", "low", "close"]]

def reconcile(dukascopy_df: pd.DataFrame, pepperstone_df: pd.DataFrame) -> dict:
    aligned = dukascopy_df.join(pepperstone_df, how="inner", lsuffix="_duka", rsuffix="_pep")
    close_diff = (aligned["close_duka"] - aligned["close_pep"]).abs()
    pct_diff   = (close_diff / aligned["close_pep"])

    report = {
        "n_bars_compared":      len(aligned),
        "mean_abs_diff_usd":    close_diff.mean(),
        "max_abs_diff_usd":     close_diff.max(),
        "pct_bars_diff_gt_0.5usd": (close_diff > 0.5).mean(),
        "pct_bars_diff_gt_1pct":   (pct_diff > 0.01).mean(),
    }
    print("\n=== CROSS-SOURCE RECONCILIATION (Dukascopy vs Pepperstone MT5) ===")
    for k, v in report.items():
        print(f"  {k:<28} {v}")

    # If discrepancy is material, your backtest edge may not transfer 1:1 to live fills.
    if report["pct_bars_diff_gt_0.5usd"] > 0.02:
        print("⚠️  >2% of bars differ by >$0.50 between sources — investigate before trusting backtest EV on live data.")
    return report
```

### 5D: Point-in-time feature store discipline (🆕, prevents a subtle leakage class v2.0 didn't name)

Beyond the lookahead checks v2.0 already planned (`test_lookahead.py`), keep every external data source (FRED, COT, DXY) in a **point-in-time** table: store both the *value* and the *timestamp it was actually published/available*, not just the date it describes. FRED's DFII10 for date D is not knowable until D+1; COT for the Tuesday close isn't published until the following Friday 3:30pm ET. v2.0's `shift(1)` patterns are the right idea but are easy to get subtly wrong (e.g., shifting by 1 calendar day instead of 1 *publication lag*, which differs by series). A minimal point-in-time table:

```python
# core/data/point_in_time_store.py
import pandas as pd

def store_point_in_time(series_name: str, value_date: pd.Timestamp,
                          published_at: pd.Timestamp, value: float) -> dict:
    """One row per observation. NEVER overwrite — append only, so you can always
    reconstruct 'what was known as of timestamp T' for any T, which is what your
    backtest needs to be honest and what a regulator/auditor would ask for anyway."""
    return {"series": series_name, "value_date": value_date, "published_at": published_at, "value": value}

def as_of(df: pd.DataFrame, query_time: pd.Timestamp) -> pd.DataFrame:
    """The only correct way to join external data into your feature matrix:
    filter to rows whose published_at <= query_time, then take the latest such row
    per series. Anything else is a potential leakage path."""
    visible = df[df["published_at"] <= query_time]
    return visible.sort_values("published_at").groupby("series").tail(1)
```
