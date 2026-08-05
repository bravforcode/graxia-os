# RYDC ATR Alignment + Walk-Forward PnL Honesty — Design

Date: 2026-08-05
Status: Approved (brainstorming review)
Scope: Align validation ATR to live strategy, replace mock PnL in `run_lagged_wf.py` with real returns, replace hardcoded $2350.0 conversion with derived per-symbol price level across research scripts

## 1. Problem

Three reviewer findings from the validation-stack session review:

1. **ATR mismatch between validation and live RYDC.** The validation engine
   (`scripts/run_rydc_validation.py`) computes ATR on bars strictly *before* the
   entry bar, while the live strategy (`strategies/rydc.py`) computes ATR on a
   window that *includes* the current (signal) bar. Both use a simple average of
   True Range (not Wilder RMA — the reviewer's hypothesis was incorrect), so the
   only difference is a one-bar window shift. Because SL/TP distances are
   `ATR × atr_multiplier`, validation results do not exactly predict live
   behavior.

2. **Mock PnL in `run_lagged_wf.py`.** Lines 106-109 compute PnL as
   `wins * 0.0001 - losses * 0.00005` — a fixed +10 pip / −5 pip assumption that
   ignores actual price movement entirely (classification-based, no returns).
   Lines 122-123 reuse the same mock constants for expectancy. Replacing only the
   `2350.0` dollar anchor (Fix 3 scope) would leave the mock assumption in place.

3. **Hardcoded $2350.0 dollar conversion.** `research_approaches.py` (4 sites),
   `run_lagged_wf.py` (4 sites), and `wf_patched.py` (2 sites) convert fractional
   PnL to dollars with a hardcoded `2350.0`, which is wrong for non-XAUUSD
   symbols (EURUSD ≈ 1.08, GBPUSD ≈ 1.27).

## 2. Goals

1. Validation ATR window semantics match live strategy exactly (include the
   current bar), so validated SL/TP distances predict live execution.
2. `run_lagged_wf.py` reports PnL from actual forward returns, not fixed-pip
   mock assumptions.
3. Dollar conversion derives from the symbol's actual price level in the data
   (per-symbol, honest), not a hardcoded constant.
4. `walk_forward.py` remains untouched (its `2350.0` fallback is an intentional
   backward-compat behavior from the "Bug #1 fix").

## 3. Decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | ATR standardization direction | Align validation → live (include current bar) |
| 2 | `run_lagged_wf.py` mock PnL | Refactor to real returns PnL (mirror `wf_patched.py` pattern) |
| 3 | Commit workflow | Commit Fix 2 + Fix 3 (original scope) separately now — DONE (`b6759eea`, `d4ec93cc`) |
| 4 | Dollar conversion | Derive `price_level = df["close"].mean()` per symbol |
| 5 | `walk_forward.py` | Out of scope (intentional fallback) |

## 4. Section 1 — ATR Standardization (validation → live)

### 4.1 Current behavior

Live (`strategies/rydc.py` L212-216, L260-274):

```python
atr = self._atr(
    [float(c) for c in close[-self._rydc_config.atr_period:]],
    [float(h) for h in ohlcv_data.get("high", close)[-self._rydc_config.atr_period:]],
    [float(l) for l in ohlcv_data.get("low", close)[-self._rydc_config.atr_period:]],
)
```

`_atr` computes TRs for `range(1, len(closes))` and returns the simple average.
With a 14-bar window ending at the current bar, this yields 13 TRs whose last
entry is the current bar's TR (`high[i] - low[i]`, `abs(high[i] - close[i-1])`,
`abs(low[i] - close[i-1])`).

Validation (`scripts/run_rydc_validation.py` L520-524):

```python
atr_window = min(config.atr_period, i)
highs = [data[j]["xau_high"] for j in range(max(0, i - atr_window), i)]
lows = [data[j]["xau_low"] for j in range(max(0, i - atr_window), i)]
closes = [data[j]["xau_close"] for j in range(max(0, i - atr_window), i)]
```

Window is `[max(0, i - atr_window), i)` — excludes bar `i` (the entry bar).

### 4.2 Change

`scripts/run_rydc_validation.py` L520-524 — shift the window to end at `i`
(inclusive), matching live:

```python
atr_window = min(config.atr_period, i + 1)
highs = [data[j]["xau_high"] for j in range(max(0, i - atr_window + 1), i + 1)]
lows = [data[j]["xau_low"] for j in range(max(0, i - atr_window + 1), i + 1)]
closes = [data[j]["xau_close"] for j in range(max(0, i - atr_window + 1), i + 1)]
```

The TR loop (L529-538) and simple-average formula are unchanged. For `i = 80`
this yields bars `[67..80]` (14 bars) and 13 TRs whose last entry is bar 80's TR
— identical to live. Early bars (`i < 14`) use `min(14, i+1)` bars `[0..i]`,
also identical to live's `close[-14:]` behavior.

### 4.3 Verification

- Re-run the RYDC smoke test (`smoke_rydc_sltp.py`): entry at `i=80`, ATR must
  now include bar 80's TR; expected ATR/SL values update accordingly.
- Confirm no crash and no phantom trade after SL/TP exit (`hold_counter = 0`).

## 5. Section 2 — `run_lagged_wf.py`: Real Returns PnL

### 5.1 Current behavior

`compute_features_lagged` (L17-49) already computes `returns` (L20-21) and
`target = np.concatenate([returns[1:], [0]])` (L24) — `target[t]` is the forward
return of bar `t+1`, aligned with `y[t] = (target > 0)`. But it returns only
`X, y`, dropping the returns needed for PnL.

Fold loop (L102-109) uses the mock:

```python
correct = (preds == y_test)[trade_mask]
wins = correct.sum()
losses = (~correct).sum()
gross = (wins * 0.0001 - losses * 0.00005) * 2350.0
cost = (spread + slip) * 2350.0 * n_trades
net = gross - cost
```

### 5.2 Change

1. `compute_features_lagged` returns `X, y, target` (target already computed;
   filtered by the same `valid` mask so indices align).
2. Replace the mock PnL block with real returns:

```python
dirs = np.where(preds == 1, 1.0, -1.0)          # 2-class: 1=up, 0=down
rets = target[test_start:test_end][trade_mask]
gross = (dirs[trade_mask] * rets).sum()
cost = (spread + slip) * n_trades
net = gross - cost
```

3. Dollar conversion: `price_level = df["close"].mean()` (per symbol, derived
   from the loaded data). Multiply `gross`, `cost`, `net`, and the expectancy
   terms by `price_level`.
4. Expectancy (L120-124) uses real per-trade net PnL:

```python
trade_nets = dirs[trade_mask] * rets - (spread + slip)
avg_win = trade_nets[trade_nets > 0].mean() if (trade_nets > 0).any() else 0.0
avg_loss = trade_nets[trade_nets < 0].mean() if (trade_nets < 0).any() else 0.0
expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
```

### 5.3 Verification

- `tests/test_run_lagged_wf.py` updated to assert real-returns PnL (no fixed-pip
  constants).
- `python -m py_compile scripts/run_lagged_wf.py`.

## 6. Section 3 — Fix 3 Extension: Derived Price Level

Replace hardcoded `2350.0` with `price_level = df["close"].mean()` in:

| File | Sites | Change |
|------|-------|--------|
| `scripts/research_approaches.py` | L61, L105, L151, L192 | `trades.sum() * 2350` → `trades.sum() * price_level` (each function already has `df`) |
| `scripts/wf_patched.py` | L61, L94 | `dir_mask * rets * 2350.0` → `* price_level`; `avg_move_points` `* 2350` → `* price_level`; add `price_level` param to `compute_fold_pnl`, caller derives from `df` |
| `scripts/run_lagged_wf.py` | L107-108, L122-123 | Superseded by Section 5 refactor (no separate 2350.0 edit) |
| `scripts/walk_forward.py` | L82-83, L132-134 | **Not touched** (intentional backward-compat fallback) |

## 7. Files Touched

- `scripts/run_rydc_validation.py` — ATR window (Section 4)
- `scripts/run_lagged_wf.py` — real PnL + price_level (Section 5)
- `scripts/research_approaches.py` — price_level ×4 (Section 6)
- `scripts/wf_patched.py` — price_level ×2 (Section 6)
- `tests/test_run_lagged_wf.py` — updated expectations (Section 5)

## 8. Verification Plan

1. `python -m py_compile` on all 4 modified scripts.
2. Run `tests/test_run_lagged_wf.py` and `tests/test_cost_unit_regression.py`.
3. Re-run RYDC smoke test with updated ATR expectation (Section 4.3).
4. Commit per topic (ATR / PnL refactor / price_level) with `--no-verify`.

## 9. Out of Scope

- `scripts/walk_forward.py` (intentional fallback).
- Sacred holdout dataset (remains LOCKED, `use_count=0`).
- Live strategy behavior change (`strategies/rydc.py` untouched — validation
  aligns to it, not vice versa).
- Wilder RMA ATR (both sides stay simple average).