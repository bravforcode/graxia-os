# PHASE 3 — MATHEMATICAL CORRECTNESS AUDIT
*Per R8, R11, R13, R14. Every formula re-derived by hand. Decimal arithmetic used to avoid float ambiguity.*

---

## 3.1 — Return Calculation

- `backtest_suite.py:24`: `df['returns'] = df['close'].pct_change()` → **simple returns**, `close[t]/close[t-1] - 1`. Log returns not used.
- Bar correctness: paired with `signal.shift(1)` (`backtest_suite.py:25`) → return at t paired with signal from t-1. **Alignment correct.**
- Units: returns are in **fraction** (e.g. 0.0012), reported as `total_return_pct = strat.sum() * 100` (`backtest_suite.py:96`). Consistent within `backtest_suite.py`.
- **Inconsistency**: `backtest/engine.py:909` computes `return_pct = pnl / notional * 100` where `notional = entry_price * quantity` → this is a **trade-level notional return**, not a bar return. The two "return" notions are not mixed in one formula (good), but a reader comparing `backtest_suite.py` `%` with engine `return_pct` must know they are different quantities.

## 3.2 — Transaction Cost Model (HIGHEST PRIORITY) — RE-DERIVED FROM FIRST PRINCIPLES

### Step 1 — Raw inputs

- Spread: `backtest/dynamic_spread_model.py:9-31` defines session-aware spread **in pips** (asian=3.0, london=1.5, ny=1.5, overlap=1.2, closed=5.0 for XAUUSD).
- Conversion to price: `backtest/engine.py:726` `spread = Decimal("0.01") * spread_pips`. For XAUUSD pip = $0.01 (1 pip = 1 cent on gold), so **`0.01 * pips` is the correct XAUUSD pip→price conversion. ✓ for XAUUSD only.**
- Commission: `backtest/engine.py:135` `commission_per_lot=3.5` (currency: USD, per side).
- Lot size: `InlineContractSpec.for_symbol("XAUUSD")` (`engine.py:79`) `trade_contract_size=100` (100 oz per lot). EURUSD `contract_size=100_000`.

### Step 2 — Trace `execution/cost_model.py:32-51`

```python
spread_cost   = spread_points * spread_mult * contract_size * volume   # line 42
slippage_cost = spread_points * slippage_mult * contract_size * volume  # line 43  ← SAME INPUT
commission    = commission_per_lot * commission_mult * volume           # line 44
```

`spread_points` is passed from `engine.py:744` as `spread_points=spread` where `spread = 0.01 * spread_pips` (a **price-quantity**, not "points"). So the variable is **misnamed** but the value fed in is the price-spread.

### Step 3 — Hand re-derivation (XAUUSD, London, volume=0.50 lot)

| Quantity | Value | Source |
|---|---|---|
| spread_pips | 1.5 | `dynamic_spread_model.py:10` |
| spread (price) | 0.015 | `0.01 × 1.5` (`engine.py:726`) |
| contract_size | 100 | `InlineContractSpec` XAUUSD |
| volume | 0.50 | example |
| **spread_cost** | **0.75** | `0.015 × 100 × 0.50` |
| **slippage_cost** | **0.75** | `0.015 × 100 × 0.50` — **slippage uses spread as input → slippage ≡ spread** |
| commission | 1.75 | `3.5 × 0.50` |
| **TOTAL round-trip** | **3.25** | |

**Reality check vs `SUMMARY.md:14`**: SUMMARY claims `$0.17 spread + $0.39 slippage P90 = $0.56/trade`. The cost_model code path produces `$0.75 + $0.75 = $1.50` for a 0.5-lot trade at London spread. The numbers do **not** match. Two possibilities: (a) SUMMARY.md used a different cost path (`scripts/simulate_fills.py`, referenced in `SUMMARY.md:10`), or (b) SUMMARY's trade size/volume differs. **This is a discrepancy between the documented "fixed" cost model and the engine's actual cost_model — flag per R16.**

### Step 4 — Cross-check: EURUSD unit correctness

EURUSD pip = 0.0001. A 0.5-pip spread = 0.00005 in price.
- `engine.py:726` produces `spread = 0.01 × 0.5 = 0.005`.
- But the *actual* EURUSD price-spread for 0.5 pip is **0.00005**.
- **RATIO: 0.005 / 0.00005 = 100×.** The `0.01 * spread_pips` conversion is correct for XAUUSD (where pip=$0.01) but **overstates EURUSD/GBPUSD/AUDUSD/NZDUSD spread by 100×** (their pip = 0.0001, so the conversion factor should be 0.0001, not 0.01).

**This is a confirmed cost-unit bug for every FX pair except JPY pairs (pip=0.01) and XAUUSD.** For USDJPY, `0.01 × pips` happens to be correct (pip=0.01). For 5-digit FX majors it is **100× too large** → backtest drastically over-charges spread on EURUSD/GBPUSD etc., which would make those pairs look *worse* than reality (error direction: against the strategy — per R, the direction nobody debugs, but here it is conservative so it does not inflate edge).

### 3.2 Step 3 — "Was the ~2000× cost bug fixed?" (per R13)

`SUMMARY.md:10` claims a prior `simulate_fills.py` ms/ns bug was fixed (50,000,000ms vs 50ms). **I cannot find a before/after diff artifact or commit in this session** (the fix is asserted in `SUMMARY.md`, a self-report — R5 says self-reports are not evidence). `scripts/simulate_fills.py` was not opened this phase. **Verdict: `[FIX UNVERIFIED — only current state of cost_model confirmed; the historical ms/ns bug's fix cannot be independently confirmed without the prior version or a diff]`.**

However, a **new** (different) cost issue is confirmed: the `slippage_cost = spread_points × …` line (`cost_model.py:43`) makes slippage numerically equal to spread, which is not a real slippage model — it is a placeholder. Real slippage depends on order size vs liquidity, not on spread. **`[BUG CONFIRMED — cost_model.py:43 uses spread as slippage input; slippage is not independently modeled]`.**

## 3.3 — Performance Metrics Formulas

Source: `backtest/metrics.py`.

| Metric | Formula in code | Correct formula | Match? | Annualization |
|---|---|---|---|---|
| Sharpe | `_sharpe_ratio` (`metrics.py:245-261`): `mean(excess)/std × sqrt(annual_trading_days)` | `mean(r)/std(r)×sqrt(N)` | ✓ structure | **`annual_trading_days=252` (`metrics.py:77`) — but equity curve is per-BAR (M15), not per-DAY** |
| Sortino | `metrics.py:264-283`: downside-deviation variant | ✓ | ✓ structure | same 252 issue |
| Max Drawdown | `_calculate_drawdown` (`metrics.py:197-231`) on equity_curve | `max(peak-trough)/peak` | ✓ | n/a |
| Win Rate | `metrics.py:102`: `winning/total` | `count(r>0)/count(r≠0)` | ✓ (treats pnl==0 as non-win, fine) | n/a |
| Profit Factor | `metrics.py:126`: `gross_profit/gross_loss`, `inf` if loss=0 | ✓ | ✓ | n/a |
| Calmar | `metrics.py:167`: `cagr / max_drawdown_pct` | ✓ | ✓ | n/a |
| IC / PSR / DSR | **`[NOT IN metrics.py]`** | — | **ABSENT** | — |

### Annualization factor — BUG

`metrics.py:156` calls `_sharpe_ratio(returns, rf, annual_trading_days=252)`. But `returns` is extracted from `equity_curve` per-*point* (`metrics.py:234-242`), and the equity curve has one point **per bar** (M15 = 4 bars/hour ≈ 96 bars/day for 24h FX, or ~5760/year if 24h). Applying `sqrt(252)` to per-bar returns **under-annualizes by a factor of ~`sqrt(5760/252)` ≈ 4.8×** for 24h FX.

- For M1: correct factor ≈ `sqrt(252 × 24 × 60) ≈ 602` (per protocol 3.3). Code uses `sqrt(252) ≈ 15.9`. **Under-reporting Sharpe by ~38×.**
- This is the *opposite* of the protocol's feared inflation — it **deflates** the reported Sharpe. So a reported Sharpe of 1.31 (`results/backtest_suite_20260626_164814.json` XAUUSD Momentum) would, if annualized correctly on per-bar returns, be ~50. **Which is itself proof of a different bug** (see 3.6).

**However**: `scripts/backtest_suite.py:89` computes Sharpe with `np.sqrt(252*96)` (= `sqrt(24192)` ≈ 155.5) — **a different, more-correct factor**. So `backtest_suite.py` and `metrics.py` use **different annualization constants for the same metric**. This is Phase 18.2 (duplicated logic) and a Phase 8 parity concern.

## 3.4 — Signal/Prediction Direction

- `core/enums.py`: `SignalType.BUY`/`SELL`, `PositionType.LONG`/`SHORT`.
- `backtest/engine.py:121-125` `_exec_side`: `BUY→FillSide.BUY`, else `SELL`.
- `execution/fill_model.py:44-47` `simulate_entry`: BUY → `ask + slippage`, SELL → `bid - slippage`. **Convention consistent end-to-end ✓.**
- Positive model prediction → buy? `[NOT TRACED into ml/pipeline.py prediction→order this phase]` → P1.

## 3.5 — Position Sizing Mathematics

`backtest/engine.py:92-118` `_historical_size`:
```
risk_budget = equity × risk_per_trade_bps / 10000
stop_distance = |entry - stop_loss|
ticks = stop_distance / tick_size
one_lot_loss = ticks × tick_value
raw_volume = risk_budget / one_lot_loss
round DOWN to volume_step; reject if < volume_min
```
- Floor at `volume_min`: ✓ (`engine.py:116-117`).
- Max lot cap: `InlineContractSpec.volume_max=100` (`engine.py:70`) exists but **`_historical_size` does NOT check `volume_max`** — only `volume_min`. **`[BUG: no upper-bound enforcement in backtest sizing]`** — flag P1. (MT5 `SYMBOL_VOLUME_MAX` check is a Phase 9.1 live item.)
- Leverage: not explicit; sizing is risk-based (fraction of equity), leverage implicit via contract_size × volume vs equity.

## 3.6 — Implausible-Result Forensic Protocol (R14)

Headline numbers from `results/backtest_suite_20260626_164814.json` (the most recent backtest on disk):

| Symbol | Strategy | total_return% | sharpe | win_rate% | PF | n_trades |
|---|---|---|---|---|---|---|
| XAUUSD | Momentum | **69.19** | 1.31 | 49.0 | 1.03 | **59999** |
| XAUUSD | MeanReversion | -4.27 | -0.17 | **6.1** | 0.99 | 59999 |
| XAUUSD | TrendFollow | 55.2 | 1.04 | 49.7 | 1.02 | 59999 |
| XAUUSD | VolBreakout | 0.0 | 0.0 | 0.0 | **Infinity** | 59999 |
| XAUUSD | RSI | -11.93 | -0.41 | 12.6 | 0.98 | 59999 |

**Forensic findings (R14):**

1. **`n_trades = 59999` for every strategy** = number of bars in the dataset. The "backtest" is **return per bar**, not per trade. There is **no position management, no cost deduction, no SL/TP** in `scripts/backtest_suite.py` — it computes `strat_ret = signal.shift(1) * returns` and sums. **This is not a backtest of a trading strategy; it is a continuously-rebalanced long/flat/short return series with zero transaction cost.** `[BUG CONFIRMED — backtest_suite.py:84-101 mislabels bar-returns as trades]`.

2. **`win_rate = 6.1%` with `total_return = -4.27%`** (MeanReversion) and **`win_rate = 12.6%` with `return = -11.93%`** (RSI): these are `% of bars where strat_ret > 0`, not win rate of trades. The label is wrong.

3. **`profit_factor = Infinity`** (VolBreakout): code path `backtest_suite.py:92` returns `inf` when `strat[strat<0].sum() == 0` — i.e., no negative-return bars. For VolBreakout this means the signal was 0 (flat) the entire window → return 0, "PF=inf" is a divide-by-zero artifact, not a real profit factor.

4. **`total_return 69.19% in ~7 days`** (Momentum): if this were real it would be ~3600% annualized. It is the *uncosted, continuously-rebalanced* bar-return sum. **Not a tradeable result.**

5. **Sharpe 1.31**: `backtest_suite.py:89` uses `sqrt(252*96)` annualization on per-M1-bar returns. For M1 the correct factor is `sqrt(252*24*60)=602`, not `sqrt(24192)=155.5`. So even the suite's own (wrong) annualization is inconsistent with its data frequency. The number is not comparable to any standard Sharpe.

**Verdict per protocol 3.6 step 7**: `[BUG CONFIRMED — cause: scripts/backtest_suite.py produces bar-return summaries mislabeled as trade metrics, with no cost model, no position management, and an inconsistent annualization factor. None of the numbers in results/backtest_suite_*.json describe a tradeable strategy's performance.]`

### Cross-reference to SUMMARY.md (R16 contradiction)

`SUMMARY.md:1` labels itself "UNVERIFIED — 26 Jun 2026" and reports **Net P&L: -$23.21** (a loss) from a *different* code path (`scripts/backtest_cost.py` / `simulate_fills.py`) with real costs. So the project's own documents contain **two contradictory performance pictures**:
- `results/backtest_suite_*.json`: +69% return, Sharpe 1.31 (uncosted bar-returns).
- `SUMMARY.md`: -$23.21 net (costed, 67 trades).

**The contradiction is explained**: the suite JSON is uncosted bar-returns; SUMMARY is a costed trade-level run. But a reader seeing only the JSON would be misled. Per R16, this conflict is named explicitly here.

## 3.7 — Deflated & Probabilistic Sharpe Ratio

- `validation/deflated_sharpe.py` exists → DSR *module* present. `[Not opened this phase]` → whether it is *called* in the reporting pipeline `[UNVERIFIED]`.
- PSR (skew/kurtosis-corrected): `[NOT FOUND as a computed metric]`. → P2.
- DSR requires a trial count (Phase 5.3 / 24.1) — the hypothesis log (Phase 17.1) is the source; `[not located]`.

---

## Phase 3 — Verdict

**STATUS: FAIL.** Three confirmed bugs:
1. **`execution/cost_model.py:43`** — slippage numerically equals spread (no real slippage model). `[BUG CONFIRMED]`
2. **`backtest/engine.py:726` `0.01 × spread_pips`** — correct for XAUUSD/JPY, **100× overstated for 5-digit FX majors**. `[BUG CONFIRMED]`
3. **`scripts/backtest_suite.py`** (the script producing `results/*.json`) — mislabels per-bar returns as trades, no cost, inconsistent annualization. **Every number in `results/backtest_suite_*.json` is non-tradeable.** `[BUG CONFIRMED]`

Plus: `metrics.py` Sharpe annualization uses `sqrt(252)` on per-bar equity curve → under-annualizes ~38× for M1 (deflation, not inflation — but still wrong). PSR absent. DSR module exists but invocation unverified.

**The previously-claimed "~2000× cost bug fix" cannot be independently verified (R13) — only the current cost_model state is confirmed, and it has its own (different) slippage bug.**
