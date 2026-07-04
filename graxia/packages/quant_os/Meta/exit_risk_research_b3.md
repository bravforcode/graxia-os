# Exit Strategy & Risk Management Research — XAUUSD M15 (B3+ Design)
**Researcher**: agent:researcher (Ruflow Project Gracia)
**Date**: 2026-06-26
**Scope**: Forward-looking research for post-B2 (B3+) exit/risk design. Does NOT modify the locked B2 config.
**Baseline (natural exits, no stop)**: WR=59%, avg_win=$11.19, avg_loss=-$14.84, price≈$4034
**B2 intervention (locked, testing Jul 23)**: hard stop $6.30 @ 0.10 lot ($0.63 price distance)

## 0. Executive Diagnosis — The Core Problem

| Metric | Value | Verdict |
| Payoff ratio (avg_win/avg_loss) | 11.19/14.84 = **0.754** | ❌ Losses 33% larger than wins |
| Expectancy/trade | 0.59×11.19 − 0.41×14.84 = **+$0.52** | ✅ Positive but thin |
| Edge source | Win rate (59%) > payoff | WR-driven, not payoff-driven |
| Risk of current shape | One WR dip → negative expectancy | Fragile |

**The entire research objective reduces to two levers:**
1. **Cap losses** — B2 stop ($6.30) attacks avg_loss: −$14.84 → ~−$6.30 (if honored). **−57% loss reduction**.
2. **Let winners run** — increase avg_win via holding period / trailing exits. Target: push payoff ratio ≥ 1.0.

If B2 succeeds (losses capped at $6.30) AND winners extend to ≥$6.30 avg, payoff flips to ≥1.0 with 59% WR → expectancy jumps from +$0.52 to **+$2.40/trade** (4.6× improvement).

## 1. Empirical Baseline (XAUUSD M15, 50,000 bars, computed from `data/XAUUSD_M15.csv`)

### ATR distribution (Wilder ATR)
| ATR | Mean | Median | p25 | p75 | p90 | p95 |
| ATR(14) | $6.47 | $4.59 | $3.04 | $8.10 | $12.17 | $15.60 |
| ATR(50) | $6.46 | $4.38 | — | $8.31 | $11.75 | — |
| Per-bar range (H-L) | $6.45 | $4.29 | — | $7.67 | $12.92 | $17.93 |

**Critical**: B2 stop distance $0.63 = **0.14× median ATR**. 2×ATR exceeds $0.63 in 100% of bars. The B2 stop sits deep inside single-bar noise — it will be triggered by routine volatility, not just adverse trends. This is intentional (it's a *loss cap*, not a *technical stop*), but it means **stop-hit frequency will be high** and the test really measures "does capping losses at $6.30 beat letting the natural exit handle them?"

### Multi-bar excursion (random long entry, n=3000, gold uptrend sample — biased upward)
| Hold | MFE median | MAE median | MAE p75 |
| 1 bar (15min) | $1.78 | $1.78 | $3.89 |
| 2 bars | $2.59 | $2.63 | $5.68 |
| 3 bars | $3.26 | $3.15 | $6.98 |
| 4 bars | $3.78 | $3.71 | $8.33 |
| 8 bars | $5.52 | $5.33 | $11.74 |

**Interpretation**: MFE ≈ MAE at 1-2 bars (no directional edge on random entries). At 4-8 bars MFE slightly exceeds MAE (uptrend drift). The strategy's 59% WR must come from *signal selection*, not holding-period drift. **Holding longer does NOT structurally increase avg win unless the signal has persistent directional bias** — this must be tested on actual strategy signals, not random entries.

### First-touch probability (within 4 bars, random long)
| Target ±$ | P(hit +target first) | P(hit −target first) |
| ±$0.63 (1R at B2) | 79% | 21% |
| ±$1.00 | 71.5% | 28.3% |
| ±$1.50 | 63.9% | 34.5% |
| ±$2.00 | 57.8% | 36.9% |

⚠️ The 79/21 split is **uptrend-biased** (2024-25 gold bull). Do not treat as direction-agnostic. For shorts it inverts.

## 2. Advanced Exit Strategies

### 2.1 Trailing Stops — Ranked for Gold M15

| Method | Formula | Pros | Cons | Verdict for gold M15 |
| **ATR trailing (2× ATR(14))** | `trail = close − 2×ATR(14)` (long); update only higher | Adapts to vol regime; standard; lets winners run in trending bars | Whipsaws in chop; ATR(14)=$4.59 → 2×=$9.18 stop = huge vs $6.30 budget | **Best for TREND regimes** |
| **Chandelier Exit (3× ATR(14) from highest high since entry)** | `CE = HH_since_entry − 3×ATR(14)` | Designed for trends; exits on vol-expansion reversal; captures big runs | 3×ATR = $13.8 — too wide for $6.30 risk budget at 0.10 lot | **Best for swing/runners** (needs wider initial stop) |
| **Fixed-$ trailing ($0.63 / $1.00)** | `trail = peak − $X` | Simple, predictable, matches B2 risk unit | No vol adaptation; gets stopped by normal M15 noise ($1.78 median range) | **Poor** — too tight, high churn |
| **Percentage trailing (0.5% of price)** | `trail = peak × 0.995` | Scales with price level | At $4034, 0.5% = $20 — enormous vs $6.30 | **Poor** at current gold price |

**Recommendation**: ATR-trailing is structurally best for gold M15, **BUT** it requires a wider initial stop than $6.30. A 2×ATR stop at median conditions = $9.18 price distance = **$91.80 risk at 0.10 lot** — 14.6× the B2 budget. ATR-trailing belongs in **B3 with a re-sized risk budget**, not as a patch on B2.

**For B2-adjacent testing**: a *fixed-$ breakeven + small trailing* hybrid is the only trailing that fits the $6.30 envelope (see 2.5).

### 2.2 Partial Exits (scale out) — EV Analysis

**Config A**: 50% off at +1R ($+6.30), 50% run with trailing stop.
**Config B**: 33% at +1R, 33% at +2R, 33% trailing.
**Config C**: 50% at +1R, 50% held to natural signal exit.

**EV math (using baseline WR=59%, current natural avg_win=$11.19)**:
- Current (no scale): E[win] = $11.19 (full position, natural exit).
- Config A: 50% locks $6.30. For the runner half: if avg runner outcome ≥ $16.08, total avg_win ≥ $11.19. Requires the runner half to achieve ≥$16 avg — **plausible only if signal has trend persistence**. If runner avg = $8 (more likely), avg_win = 0.5×6.30 + 0.5×8 = **$7.15** — **WORSE than $11.19**.

**Key insight**: Scaling out **reduces avg_win** unless the tail of the winner distribution is fat enough that the runner half captures disproportionately large moves. On M15 gold with $1.78 median bar range, fat tails are rare. **Partial exits trade avg_win for consistency (lower variance), not for higher EV.** They help *risk-adjusted* returns (Sharpe) but usually *hurt* raw avg_win on short-horizon gold.

**Verdict**: Test it, but **expect avg_win to drop ~30-40%** ($11.19 → ~$7) with a smaller std-dev. Only adopt if the Sharpe/Calmar improvement outweighs the EV loss AND you're capital-constrained.

### 2.3 Time-Based Exits

**Rule**: Exit at close of bar N regardless of PnL.

| N (bars) | Time | Expected effect |
| 2 (30min) | Cuts losers early; caps winners | Reduces both avg_win and avg_loss; raises WR slightly |
| 4 (1hr) | Matches one full M15 cycle | Neutral — close to current natural exit |
| 8 (2hr) | Lets runs develop | Raises avg_win IF signal persistent; raises avg_loss if not |
| 16 (4hr) | Overhold risk | Winners may reverse; avg_loss grows from MAE p75=$11.74 |

**From excursion data**: MFE median plateaus around 4-8 bars ($3.78→$5.52) while MAE keeps climbing. **Optimal time-stop candidate: 4 bars (1 hour)** — captures most of the favorable move before MAE acceleration. **But this must be measured on strategy signals, not random entries.**

**Recommendation**: Test `time_stop = 4 bars` as a *secondary* exit (only triggers if neither stop nor natural signal fires). Expected: small avg_loss reduction (cuts the long-tail losers that hang around), neutral-to-slightly-positive on avg_win.

### 2.4 Volatility-Adjusted Exits

**Rule**: In high-vol regime (ATR(14) > p75 = $8.10), tighten exit / reduce size.

Two implementations:
- **Exit-speed**: Use shorter trailing multiple in high vol (e.g., 1.5×ATR when ATR>p75, 2.5×ATR when ATR<p25). Rationale: high vol = faster mean-reversion on M15, don't give it room.
- **Position-scaling**: reduce lot size by factor `min(1, $6.30 / (2×ATR))` so dollar risk stays constant. (See §3.4.)

**Expected impact**: Reduces tail losses during vol spikes (NFP, FOMC). Estimated −20% on avg_loss during high-vol weeks, neutral on avg_win. **High value, low complexity.**

### 2.5 Breakeven Stop (move stop→entry at +1R)

**Rule**: Once price reaches +$6.30 (1R), move stop from −$0.63 to entry (risk → $0).

**First-touch data**: P(hit +$0.63 before −$0.63 within 4 bars) = 79% (uptrend-biased). So ~79% of trades reach +1R; once there, BE stop converts ~21% of would-be-winners into scratch (−$0 cost) but **eliminates the −$6.30 outcome on trades that gave back full profit**.

**EV impact**: Trades that reach +1R then reverse: currently they may exit at small loss or small win. With BE: they exit at $0. Net effect depends on the mass of "reach 1R then round-trip" trades.
- Best case: converts the worst winners/give-backs into $0 → **avg_loss shrinks** (the round-trippers that ended negative now = $0), avg_win slightly lower (round-trippers that ended slightly positive now = $0).
- Likely net: **avg_loss −10-15%, avg_win −5%, WR up ~3-5pp, expectancy roughly flat-to-slightly-positive.**

**Verdict**: **Best risk-free improvement available within the $6.30 budget.** Pure downside protection. Implement as the #1 exit enhancement. The only cost is losing some marginal winners.

## 3. ATR-Based Stop Loss (alternative to fixed $6.30)

### 3.1 Standard ATR multiples for gold
| Multiple | Stop distance (median ATR $4.59) | $ risk @ 0.10 lot | Fit |
| 1.0× | $4.59 | $45.90 | Too wide vs $6.30 budget |
| 1.5× | $6.88 | $68.84 | Standard forex; wide for this budget |
| 2.0× | $9.18 | $91.80 | Common "gold standard" — but 14.6× B2 |
| 3.0× | $13.77 | $137.68 | Swing/position only |

**Industry standard for gold**: 2× ATR for intraday, 3× ATR for swing. **But these are calibrated to risk ~1% of a $50k account ($500), not $6.30.** At $500 risk budget, 2×ATR median = $9.18 price stop → lot = $500/$9.18/100 = **0.54 lot**. This is the *consistent* way to use ATR stops.

### 3.2 Dynamic stop = max($6.30, 2×ATR) — does it help?

**No, it hurts the B2 hypothesis.** `max($6.30, 2×ATR)` = 2×ATR in ~100% of bars (since 2×ATR ≥ $0.63 always, and at 0.10 lot 2×ATR ≈ $9 price = $90 risk >> $6.30). This degenerates to a pure ATR stop and **abandons the $6.30 loss cap** — which is the entire point of B2.

The correct dynamic formulation keeps the **dollar risk constant** and adjusts the *lot size*, not the stop distance:
```
stop_price_distance = 2 × ATR(14)        # vol-aware
lot = risk_budget_dollars / (stop_price_distance × 100)   # keep $ risk fixed
```
At $6.30 risk budget, median ATR: lot = 6.30 / (2×4.59×100) = **0.0069 lot** → below broker min 0.01 and below statistical resolution. **Infeasible at $6.30 budget.**

**Conclusion**: ATR-based stops and the $6.30 budget are **incompatible at 0.10 lot**. ATR stops require a **larger risk budget** (≥$45/trade) and smaller lots (≤0.014). This is a **B3+ redesign**, not a B2 tweak. **Recommend: test ATR stop as a separate B3 arm with $50-$90 risk budget.**

### 3.3 ATR vs fixed-$ — avg loss reduction comparison

| Stop type | Expected avg_loss | Mechanism |
| Fixed $6.30 (B2) | ~−$6.30 (+slippage) | Hard cap; high stop-hit frequency |
| 2×ATR (median $9.18) | ~−$9 to −$12 | Wider stop survives noise; fewer false hits but bigger loss when real |
| 2×ATR with lot resized to $6.30 risk | ~−$6.30 | Same dollar cap, fewer false stops — **but infeasible lot size** |

**The real question B2 answers**: does a tight hard cap ($6.30) outperform the natural exit (avg_loss −$14.84) net of the false-stop churn it introduces? If B2's avg_net ≥ $0.40, the cap wins despite churn. If not, the stop is *too tight* and the contingency ($7.00) or an ATR redesign is needed.

## 4. Position Sizing for Maximum Profit

### 4.1 Kelly Criterion (current edge)
```
p = 0.59, q = 0.41, b = avg_win/avg_loss = 11.19/14.84 = 0.754
f* = (b·p − q) / b = (0.754×0.59 − 0.41) / 0.754 = (0.445 − 0.41)/0.754 = 0.0463
```
| Fraction | Risk % | $ risk @ $50k | Lot @ $6.30 stop (0.10 lot = $6.30) |
| Full Kelly | 4.63% | $2,313 | 36.7 lot ❌ insane |
| **Half Kelly** | **2.31%** | **$1,157** | **18.4 lot** ❌ still insane |
| Quarter Kelly | 1.16% | $578 | 9.2 lot ❌ |
| 1% fixed (golden rule) | 1.00% | $500 | 7.94 lot |
| 0.5% (conservative) | 0.50% | $250 | 3.97 lot |

**⚠️ Critical**: Kelly recommends risk *percentages*, but the lot sizes above assume the $6.30 stop translates to $6.30 risk at 0.10 lot. **18-36 lots of XAUUSD = $1.8M-$3.7M notional — absurd vs $50k account.** The Kelly fractions are *correct for the edge* but the stop is so tight that sizing to 2.3% risk would mean enormous leverage. **This is the danger of a 0.14×ATR stop: it makes Kelly suggest dangerous leverage.**

### 4.2 Recommended: Fractional Kelly with a leverage cap
**Use Quarter-Kelly (1.16%) BUT cap by notional leverage ≤ 5× account.**
- Quarter Kelly $ risk = $578.
- At $6.30 stop / 0.10 lot: naive lot = 9.2.
- Leverage cap: 5×$50k = $250k notional / ($4034×100/lot) → max lot = 250000/(4034×100) = **0.62 lot**.
- **Effective lot = min(9.2, 0.62) = 0.62 lot.** $ risk at 0.62 lot with $0.63 stop... wait, lot scales the stop too.

**Cleaner framework (recommended)**: Decouple. Pick risk% and let lot be derived from a *volatility-appropriate* stop:
```
risk_dollars = 0.25 × Kelly% × equity = ~$578
stop_price = 2 × ATR(14)              # vol-appropriate, ~$9.18 median
lot = risk_dollars / (stop_price × 100) = 578 / 918 = 0.63 lot
notional = 0.63 × 100 × 4034 = $254k  ≈ 5× leverage  ✅
```
This is the **B3 coherent sizing**: Quarter-Kelly risk, 2×ATR stop, leverage-capped lot. Risk per trade ≈ $578 (1.16%), stop ≈ $9-12.

### 4.3 Why NOT full/half Kelly now
- Edge estimate (59% WR, payoff 0.75) is from **in-sample / limited prospective data**. Kelly is extremely sensitive to parameter error: a 5pp WR drop (59→54) with payoff 0.75 → f* = (0.75×0.54−0.46)/0.75 = **−0.075 (negative — no bet)**.
- Half/Full Kelly with mis-estimated edge → catastrophic drawdown. **Quarter-Kelly is the academic consensus for estimated edges** (Maclean-Thorp-Ziemba).

### 4.4 Volatility-targeted sizing
```
target_risk_dollars = 1% × equity = $500
scale = clamp( $500 / (2×ATR(14)×100×min_lot_risk), 0.5, 1.5 )
lot = base_lot × scale      # shrink in high ATR, grow in low ATR
```
Keeps dollar risk ~constant across vol regimes. **Reduces avg loss in volatile periods, raises avg win in calm periods.** Pair with the regime filter (§5).

### 4.5 Max position size ($50k, $6.30 stop)
- Broker margin (Pepperstone Razor XAUUSD ~1:500 retail, 1:30 EU): at 1:30, max notional = $1.5M → max lot = 1500000/403400 = **3.72 lot**.
- Risk-based: 1% golden rule = $500 → at $6.30 stop/0.10lot = **7.94 lot** (but this is 32× leverage — violates sanity).
- **Practical max = 0.62 lot** (5× leverage cap, quarter-Kelly). This is the binding constraint.

## 5. Multi-Bar Holding Strategy

### Current vs alternatives (excursion medians, random entries)
| Hold | MFE med | MAE med | Net edge (MFE−MAE) | Note |
| 1 bar (current) | $1.78 | $1.78 | $0.00 | No drift edge; WR comes from signal |
| 2 bars | $2.59 | $2.63 | −$0.04 | Slight adverse |
| 3 bars | $3.26 | $3.15 | +$0.11 | Crossover |
| **4 bars** | **$3.78** | **$3.71** | **+$0.07** | Best risk/reward band |
| 8 bars | $5.52 | $5.33 | +$0.19 | More room but more time-at-risk |

**Hypothesis**: extending 1→4 bars raises avg_win (winners run further) but also raises avg_loss (losers dig deeper). The **net** depends on whether the signal's winners are more persistent than its losers.

**How to test (cannot do during B2)**: On the *historical* signal set (pre-B2), re-label each trade with the close at bar +2,+3,+4 and recompute avg_win/avg_loss/WR. If avg_win grows faster than avg_loss as N increases, extend the holding period. **Expected: avg_win +30-50%, avg_loss +20-30% → payoff improves if WR holds.**

**Recommendation**: 4-bar (1-hour) hold is the prime candidate. **Test first on historical signals; do NOT change B2's 1-bar hold.**

## 6. Regime-Adaptive Risk

### 6.1 VIX-based sizing
- VIX>30 → reduce size 50%. (Note: VIX is equity vol; for gold use **GVZ or ATR percentile**.) Better: use XAUUSD's own ATR percentile.
- **Implement**: `size_scale = 1.0 if ATR_pctile<75 else 0.5`. Cuts exposure in the top-quartile vol bars where MAE p75 = $8.33+.

### 6.2 News-event blackout (±30min)
- NFP (1st Fri), CPI, FOMC, FOMC minutes, Powell speeches.
- **Rule**: no new entries ±30min around release; existing positions keep stops (gap risk accepted).
- The B2 plan already flags Jul 4 NFP & Jul 30 FOMC for monitoring. **B3 should hard-block entries in these windows.**
- Expected: eliminates the gap-through tail (the −$14.84 outliers are likely news-driven). **High-impact, zero-cost.**

### 6.3 Session-based risk
| Session (UTC) | XAUUSD character | Size |
| Asia (00:00-07:00) | Low vol, range-bound, false breakouts | ×0.5 |
| London (07:00-16:00) | Trend-initiating | ×1.0 |
| London/NY overlap (12:00-17:00) | Highest liquidity, best trends | **×1.25** |
| NY late (17:00-21:00) | Exhaustion, reversals | ×0.75 |

**From data**: bars at 22:30-23:45 UTC show volume spikes (1500+) and large ranges — these are the Asian-open/rollover moves. Size up there only with trend confirmation.

## 7. Priority Ranking — What to Implement FIRST (post-B2)

| # | Strategy | Expected impact | Complexity | Dependency |
| **1** | **Breakeven stop at +1R** | avg_loss −10-15%, WR +3-5pp, ~risk-free | Low | None — fits $6.30 budget |
| **2** | **News-event blackout ±30min** | Removes gap-tail losses; avg_loss −15-25% | Low | Event calendar feed (repo has `events/`) |
| **3** | **Vol-targeted sizing (ATR percentile)** | avg_loss −20% in high-vol; consistency ↑ | Low | ATR percentile calc |
| **4** | **4-bar holding period** (test on historical signals) | avg_win +30-50% if signal persistent | Med | Historical re-label study |
| **5** | **ATR trailing 2× (B3 arm, wider budget)** | Biggest avg_win upside in trends | Med | New risk budget ($50-90), new lot |
| **6** | **Quarter-Kelly + leverage cap (B3 arm)** | Optimal growth, controlled DD | Med | Requires ATR-stop arm first |
| **7** | **Session-based sizing** | Mild WR/consistency gain | Low | Session tagger |
| **8** | **Partial exits (scale-out)** | avg_win ↓30%, variance ↓ — adopt only if Sharpe-weighted | Low | A/B vs full exit |

**Implement 1-3 immediately after B2 evaluation regardless of verdict** (they improve any config). 4 needs a historical study. 5-6 are a coherent B3 redesign. 7-8 are polish.

## 8. Backtest Simulation Ideas (on existing per-trade data)

These run on the **historical signal set** (pre-B2) — do NOT run during the B2 paper-trade window (violates pre-register rule 3).

1. **BE-stop replay**: For each historical trade, simulate "if MFE ≥ +1R ($6.30) at any bar, exit the give-back at $0; else use natural exit." Recompute avg_win/avg_loss/WR. *Validates priority #1.*
2. **Holding-period sweep**: Re-exit every historical signal at bar +{1,2,3,4,8} close. Plot avg_win, avg_loss, WR, expectancy vs N. *Validates priority #4.*
3. **ATR-stop replay**: For each historical entry, set stop = entry ± 2×ATR(14) at entry time; exit at stop or natural signal. Recompute metrics + required lot for $50-90 risk. *Validates priority #5.*
4. **News-window filter**: Drop historical trades whose entry falls ±30min of NFP/CPI/FOMC (use `events/` store). Recompute metrics. *Validates priority #2.*
5. **Vol-regime split**: Partition historical trades by entry-bar ATR percentile (<p25, p25-75, >p75). Report avg_win/avg_loss/WR per bucket. *Validates priority #3.*
6. **Partial-exit A/B**: Config A (50%@1R, 50% natural) vs full-natural. Compare avg_win, std-dev, Sharpe, expectancy. *Validates priority #8.*
7. **Trailing-stop sweep**: Test trailing = {0.5×ATR, 1×ATR, 1.5×ATR, 2×ATR} from peak. Report avg_win/avg_loss/WR. *Validates priority #5 param.*
8. **First-touch curve**: For strategy signals (not random), measure P(MFE≥T before MAE≥T) for T = 0.5R…3R. Determines optimal BE/trail trigger. *Calibrates priorities #1, #5.*

## 9. Code Snippets

### 9.1 Breakeven stop module (priority #1)
```python
# core/breakeven_exit.py
from dataclasses import dataclass

@dataclass(frozen=True)
class BEConfig:
    r_dollars: float = 6.30          # 1R in dollars
    trigger_r: float = 1.0           # move stop to entry at +1R

def be_stop_update(position_peak_favorable: float, entry: float,
                   direction: str, current_stop: float, cfg: BEConfig) -> float:
    """Return new stop price. Long: stop rises to entry once +1R reached."""
    r_price = cfg.r_dollars / (0.10 * 100)   # $0.63 at 0.10 lot
    if direction == "long":
        if position_peak_favorable >= cfg.trigger_r * r_price and current_stop < entry:
            return entry                      # breakeven
    else:  # short
        if position_peak_favorable >= cfg.trigger_r * r_price and current_stop > entry:
            return entry
    return current_stop
```

### 9.2 ATR-percentile vol-targeted sizing (priority #3)
```python
# risk/vol_target_sizer.py
import numpy as np

def atr_percentile(atr_history: list[float], current_atr: float) -> float:
    return float(np.searchsorted(np.sort(atr_history), current_atr) / len(atr_history))

def vol_target_lot(base_lot: float, atr_pctl: float,
                   shrink_at: float = 0.75, shrink_to: float = 0.5) -> float:
    """Halve size when ATR in top quartile."""
    return base_lot * (shrink_to if atr_pctl >= shrink_at else 1.0)
```

### 9.3 News-window blackout gate (priority #2) — repo already has `events/`
```python
# events/blackout_gate.py  (extends existing event_risk_gate.py)
from datetime import datetime, timedelta

HIGH_IMPACT = {"NFP", "CPI", "FOMC", "FOMC_MINUTES", "POWELL_SPEECH"}
WINDOW_MIN = 30

def entry_blocked(signal_time: datetime, events: list[tuple[datetime, str]]) -> tuple[bool, str]:
    for evt_time, evt_type in events:
        if evt_type in HIGH_IMPACT and abs((signal_time - evt_time).total_seconds()) <= WINDOW_MIN*60:
            return True, f"blackout around {evt_type} at {evt_time}"
    return False, ""
```

### 9.4 ATR trailing stop (priority #5, B3 arm)
```python
# core/atr_trailing.py
def atr_trail_stop(peak_price: float, atr: float, mult: float, direction: str) -> float:
    if direction == "long":
        return peak_price - mult * atr
    return peak_price + mult * atr

# Usage: stop = max(initial_stop, atr_trail_stop(peak, atr14, 2.0, dir))
#        update peak each bar; stop only moves in favorable direction.
```

### 9.5 Holding-period re-label study (priority #4, historical only)
```python
# scripts/holding_period_study.py  (RUN ONLY AFTER B2 ENDS Jul 23)
import pandas as pd
def relabel_exits(signals_df, bars_df, hold_n):
    """signals_df has entry_bar_idx; bars_df is M15 OHLC. Exit at bar+hold_n close."""
    out = []
    for _, s in signals_df.iterrows():
        i = s.entry_bar_idx
        if i + hold_n >= len(bars_df): continue
        exit_px = bars_df.iloc[i+hold_n].close
        pnl = (exit_px - s.entry_price) * (1 if s.direction=="long" else -1) * 100 * s.lot
        out.append({**s.to_dict(), "exit_px": exit_px, "pnl": pnl, "hold_n": hold_n})
    return pd.DataFrame(out)
# Run for hold_n in [1,2,3,4,8]; compare avg_win/avg_loss/WR/expectancy.
```

## 10. Hard Constraints & Pre-Registration Discipline

- **B2 is LOCKED** (`Meta/pre_register_b2.md`). NONE of §2-6 may be applied to the live B2 paper trade. Any mid-period change voids the test (rule W).
- This document is **research for B3 design only**. Implementations run on historical data **after Jul 23** or in a separate B3 pre-registration.
- The repo already contains `KellySizer`, `ATRSizer`, `AntiMartingaleSizer` (`risk/position_sizer.py`) and `events/event_risk_gate.py` — much of §3,§6 is wiring existing code, not new logic.
- ATR-stop + Quarter-Kelly (§4.2, §3.2) constitute a **new risk budget** and must be pre-registered as B3 before prospective testing.

## 11. One-Line Decision Matrix

| Goal | Best single move |
| Minimize avg loss (cap) | B2 $6.30 stop (testing now) |
| Minimize avg loss (risk-free) | Breakeven stop at +1R (priority #1) |
| Maximize avg win (trend) | 2×ATR trailing, 4-bar hold (B3 arm) |
| Maximize growth rate | Quarter-Kelly + leverage cap (B3 arm) |
| Remove tail losses | News blackout ±30min (priority #2) |
| Consistency (Sharpe) | Vol-targeted sizing + partial exits |
