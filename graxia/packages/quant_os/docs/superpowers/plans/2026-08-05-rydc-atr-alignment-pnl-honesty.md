# RYDC ATR Alignment + Walk-Forward PnL Honesty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make validation ATR match live RYDC semantics (include the current bar) and replace mock/hardcoded PnL with real forward returns and per-symbol derived price levels across the research scripts.

**Architecture:** Four independent, commit-per-topic changes: (1) extract the ATR window slice in `run_rydc_validation.py` into a testable helper that ends at the current bar; (2) make `compute_features_lagged` return the aligned close-price series and compute fold PnL from real forward returns with `price_level = df["close"].mean()`; (3) replace the 4 hardcoded `* 2350` conversions in `research_approaches.py` with `* price_level`; (4) add a required `price_level` param to `wf_patched.compute_fold_pnl` and derive it from `df` in the caller. `walk_forward.py` and `strategies/rydc.py` stay untouched.

**Tech Stack:** Python 3, pandas, numpy, xgboost, pytest.

## Global Constraints

- `scripts/walk_forward.py` is NOT touched — its `2350.0` fallback is intentional backward-compat ("Bug #1 fix").
- `strategies/rydc.py` is NOT touched — validation aligns to live, not vice versa.
- Sacred holdout dataset remains LOCKED (`use_count=0`).
- Both ATR sides stay simple average of True Range — no Wilder RMA.
- Dollar conversion uses `price_level = df["close"].mean()` per symbol.
- No new dependencies; 4-space indent, type hints, snake_case (repo style).
- Commits use `--no-verify` (repo hooks time out) with Conventional Commits, e.g. `fix(quant_os): ...`.
- Run commands from `graxia/packages/quant_os` (package root).

---

### Task 1: ATR Window Alignment in run_rydc_validation.py

**Files:**
- Modify: `scripts/run_rydc_validation.py` (add `_atr_window` helper near `load_data` at L411; replace ATR slice at L520-524)
- Test: Create `tests/test_rydc_atr_window.py`

**Interfaces:**
- Consumes: `data: list[dict]` rows with `xau_high`/`xau_low`/`xau_close` keys (same shape as `load_data` returns).
- Produces: `_atr_window(data: list[dict], i: int, atr_period: int) -> tuple[list[float], list[float], list[float]]` — high/low/close slices for the window ending at bar `i` inclusive, matching live `close[-atr_period:]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rydc_atr_window.py
"""RYDC ATR alignment: validation ATR window must include the current (entry) bar,
matching the live strategy's close[-atr_period:] semantics."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from run_rydc_validation import _atr_window  # noqa: E402


def _data(n=100):
    return [
        {"xau_high": 100.0 + j, "xau_low": 99.0 + j, "xau_close": 99.5 + j}
        for j in range(n)
    ]


def test_atr_window_includes_current_bar():
    highs, lows, closes = _atr_window(_data(), 80, 14)
    assert len(closes) == 14
    assert closes[-1] == 99.5 + 80   # bar 80 (entry bar) included
    assert highs[-1] == 100.0 + 80
    assert lows[-1] == 99.0 + 80


def test_atr_window_early_bars_use_min_window():
    highs, lows, closes = _atr_window(_data(), 5, 14)
    assert len(closes) == 6          # min(14, i+1) bars [0..5]
    assert closes[0] == 99.5         # bar 0
    assert closes[-1] == 99.5 + 5    # bar 5 (current bar) included
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rydc_atr_window.py -q`
Expected: FAIL with `ImportError: cannot import name '_atr_window' from 'run_rydc_validation'`

- [ ] **Step 3: Write minimal implementation**

Add helper before `load_data` (L411):

```python
def _atr_window(data: list[dict], i: int, atr_period: int) -> tuple[list[float], list[float], list[float]]:
    """High/low/close slices for the ATR window ending at bar i (inclusive).

    Matches the live strategy's ``close[-atr_period:]`` semantics: the current
    (signal) bar is included, so the last True Range is bar i's TR.
    """
    atr_window = min(atr_period, i + 1)
    start = max(0, i - atr_window + 1)
    end = i + 1
    highs = [data[j]["xau_high"] for j in range(start, end)]
    lows = [data[j]["xau_low"] for j in range(start, end)]
    closes = [data[j]["xau_close"] for j in range(start, end)]
    return highs, lows, closes
```

Replace L520-524:

```python
        # Compute ATR
        highs, lows, closes = _atr_window(data, i, config.atr_period)
```

(The TR loop at L529-538 and the simple-average formula are unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rydc_atr_window.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_rydc_atr_window.py scripts/run_rydc_validation.py
git commit --no-verify -m "fix(quant_os): align validation ATR window to live RYDC (include current bar)"
```

---

### Task 2: run_lagged_wf.py — Real Returns PnL

**Files:**
- Modify: `scripts/run_lagged_wf.py` (`compute_features_lagged` L17-49; `run_walk_forward` L61, L102-109, L120-124)
- Test: `tests/test_run_lagged_wf.py` (pre-existing, currently RED)

**Interfaces:**
- Consumes: existing test contract `X, y, price = compute_features_lagged(df)` — 3-tuple, `price` = close-price array filtered by the same `valid` mask (len(X) == len(y) == len(price)).
- Produces: `compute_features_lagged(df) -> tuple[np.ndarray, np.ndarray, np.ndarray]`; fold PnL from real forward returns `rets_full[t] = (price[t+1] - price[t]) / price[t]`; `price_level = df["close"].mean()`.

- [ ] **Step 1: Confirm the failing test exists (pre-written)**

`tests/test_run_lagged_wf.py` already asserts:
- `test_no_hardcoded_price_constant_in_source`: `"2350.0" not in` source
- `test_compute_features_lagged_returns_aligned_price_series`: `X, y, price = compute_features_lagged(df)` with `0.5 < price.mean() < 2.0`

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_lagged_wf.py -q`
Expected: FAIL (2 failed — `2350.0` still in source; `ValueError: not enough values to unpack (expected 3, got 2)`)

- [ ] **Step 3: Write minimal implementation**

`compute_features_lagged` — add aligned price return (L45-49):

```python
    valid = ~np.isnan(features).any(axis=1)
    X = features[valid].astype(np.float32)
    y = ((target > 0)).astype(int)[valid]
    price = close[valid]  # aligned price series for real-returns PnL

    return X, y, price
```

`run_walk_forward` — unpack 3-tuple, derive price_level + forward returns (L61-67):

```python
    X, y, price = compute_features_lagged(df)
    if len(X) < 500:
        return None

    costs = COSTS.get(symbol, COSTS["XAUUSD"])
    spread = costs["spread"]
    slip = costs["slippage"]
    price_level = df["close"].mean()

    # Forward returns aligned with y: rets_full[t] = (price[t+1] - price[t]) / price[t]
    rets_full = np.zeros_like(price)
    rets_full[:-1] = np.diff(price) / price[:-1]
```

Fold loop — replace mock PnL (L102-111):

```python
            correct = (preds == y_test)[trade_mask]
            wins = correct.sum()
            losses = (~correct).sum()

            # Real P&L from actual forward returns (no fixed-pip mock)
            dirs = np.where(preds == 1, 1.0, -1.0)          # 2-class: 1=up, 0=down
            rets = rets_full[test_start:test_end][trade_mask]
            trade_nets = dirs[trade_mask] * rets * price_level - (spread + slip) * price_level
            net = trade_nets.sum()

            fold_nets.append({
                "trades": n_trades, "wins": int(wins), "losses": int(losses),
                "net": net, "trade_nets": trade_nets,
            })
```

Aggregate — replace mock expectancy (L120-124):

```python
            # Real per-trade expectancy
            win_rate = total_wins / total_trades if total_trades > 0 else 0
            all_nets = np.concatenate([f["trade_nets"] for f in fold_nets])
            avg_win = all_nets[all_nets > 0].mean() if (all_nets > 0).any() else 0.0
            avg_loss = all_nets[all_nets < 0].mean() if (all_nets < 0).any() else 0.0
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_lagged_wf.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/run_lagged_wf.py
git commit --no-verify -m "fix(quant_os): real forward-return PnL in run_lagged_wf (drop fixed-pip mock)"
```

---

### Task 3: research_approaches.py — Derived Price Level

**Files:**
- Modify: `scripts/research_approaches.py` (L61, L105, L151, L192)
- Test: Create `tests/test_research_approaches_price_level.py`

**Interfaces:**
- Consumes: each test function already receives `df` (with `close` column).
- Produces: `price_level = df["close"].mean()` inside each function; `"net": trades.sum() * price_level`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_research_approaches_price_level.py
"""Bug #3 extension: research_approaches.py must derive dollar PnL from actual price level."""

import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from research_approaches import test_session_pattern  # noqa: E402


def _src():
    return (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_approaches.py").read_text()


def test_no_hardcoded_2350_in_source():
    assert "2350" not in _src()


def _make_df(level):
    n = 300
    rng = np.random.RandomState(0)
    moves = rng.normal(0, 0.001, n)
    close = level * np.exp(np.cumsum(moves))  # same fractional moves at any level
    idx = pd.date_range("2024-01-01 08:00", periods=n, freq="h", tz="UTC")  # all bars in London session
    return pd.DataFrame({"close": close, "high": close * 1.001, "low": close * 0.999}, index=idx)


def test_net_scales_with_price_level():
    low = test_session_pattern(_make_df(1.10))["london"]
    high = test_session_pattern(_make_df(2350.0))["london"]
    assert low["trades"] == high["trades"] > 0
    ratio = high["net"] / low["net"]
    assert abs(ratio - 2350.0 / 1.10) < 1e-3  # net = trades.sum() * price_level
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_approaches_price_level.py -q`
Expected: FAIL (2 failed — `"2350"` in source; `ratio` ≈ 1, not ≈ 2136)

- [ ] **Step 3: Write minimal implementation**

In `test_mean_reversion` (before the return dict at L58):

```python
    trades = np.array(trades)
    wins = (trades > 0).sum()
    price_level = df["close"].mean()
    return {
        "trades": len(trades),
        "win_rate": wins / len(trades),
        "net": trades.sum() * price_level,  # convert to dollars
        "sharpe": trades.mean() / trades.std() * np.sqrt(min(len(trades), 252)) if trades.std() > 0 else 0,
    }
```

Same pattern in `test_momentum` (L100-107) and `test_volatility_breakout` (L146-153): add `price_level = df["close"].mean()` after `wins = (trades > 0).sum()` and change `"net": trades.sum() * 2350,` → `"net": trades.sum() * price_level,`.

In `test_session_pattern` (add before the loop at L182, change L192):

```python
    results = {}
    price_level = df["close"].mean()
    for name, trades in [("london", trades_london), ("ny", trades_ny)]:
        ...
            "net": trades.sum() * price_level,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_research_approaches_price_level.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_research_approaches_price_level.py scripts/research_approaches.py
git commit --no-verify -m "fix(quant_os): derive dollar PnL from per-symbol price level in research_approaches"
```

---

### Task 4: wf_patched.py — Derived Price Level

**Files:**
- Modify: `scripts/wf_patched.py` (`compute_fold_pnl` L38-95; caller L134-139)
- Test: Create `tests/test_wf_patched_price_level.py`

**Interfaces:**
- Consumes: `compute_fold_pnl(returns, preds, confs, spread_cost, slippage_p90, price_level, min_confidence=0.85)` — `price_level` required (no default, so no `2350.0` remains in source).
- Produces: dollar PnL scaled by `price_level`; caller `walk_forward` passes `price_level=df["close"].mean()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wf_patched_price_level.py
"""Bug #3 extension: wf_patched.py must derive dollar PnL from actual price level."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from wf_patched import compute_fold_pnl  # noqa: E402


def _src():
    return (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "wf_patched.py").read_text()


def test_no_hardcoded_2350_in_source():
    assert "2350.0" not in _src()


def test_compute_fold_pnl_scales_with_price_level():
    rng = np.random.RandomState(0)
    n = 100
    returns = rng.normal(0, 0.001, n)
    preds = rng.randint(0, 3, n)          # 3-class TB labels: 0/1/2
    confs = rng.uniform(0.8, 1.0, n)
    kwargs = dict(spread_cost=1e-5, slippage_p90=1e-5, min_confidence=0.85)
    low = compute_fold_pnl(returns, preds, confs, price_level=1.10, **kwargs)
    high = compute_fold_pnl(returns, preds, confs, price_level=2350.0, **kwargs)
    assert low["n_trades"] == high["n_trades"] > 0
    assert abs(high["gross_pnl"] / low["gross_pnl"] - 2350.0 / 1.10) < 1e-3
    assert abs(high["total_cost"] / low["total_cost"] - 2350.0 / 1.10) < 1e-3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_wf_patched_price_level.py -q`
Expected: FAIL (2 failed — `"2350.0"` in source; `TypeError: compute_fold_pnl() got an unexpected keyword argument 'price_level'`)

- [ ] **Step 3: Write minimal implementation**

Signature (L38-42) — add required `price_level` before the defaulted `min_confidence`:

```python
def compute_fold_pnl(
    returns: np.ndarray, preds: np.ndarray, confs: np.ndarray,
    spread_cost: float, slippage_p90: float,
    price_level: float,
    min_confidence: float = 0.85,
) -> dict:
```

L61:

```python
    raw_pnl_dollars = dir_mask * rets * price_level
```

L94:

```python
        "avg_move_points": round(float(np.abs(rets).mean() * price_level * 100), 1) if len(rets) > 0 else 0.0,
```

Caller (L134-139):

```python
        result = compute_fold_pnl(
            ret_test, preds, conf,
            spread_cost=spread_cost,
            slippage_p90=slippage_p90,
            price_level=df["close"].mean(),
            min_confidence=min_confidence,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_wf_patched_price_level.py tests/test_rydc_atr_window.py tests/test_run_lagged_wf.py tests/test_research_approaches_price_level.py tests/test_cost_unit_regression.py -q`
Expected: PASS (all)

Also run: `python -m py_compile scripts/run_rydc_validation.py scripts/run_lagged_wf.py scripts/research_approaches.py scripts/wf_patched.py`
Expected: no output (exit 0)

- [ ] **Step 5: Commit**

```bash
git add tests/test_wf_patched_price_level.py scripts/wf_patched.py
git commit --no-verify -m "fix(quant_os): derive dollar PnL from per-symbol price level in wf_patched"
```

---

## Self-Review

**1. Spec coverage:**
- §4 ATR standardization → Task 1 (helper `_atr_window` ends at bar `i` inclusive; loop uses it).
- §5 run_lagged_wf real PnL → Task 2 (3-tuple return, real forward returns, price_level, real expectancy).
- §6 research_approaches ×4 → Task 3; wf_patched ×2 → Task 4; run_lagged_wf 2350.0 → Task 2 (superseded); walk_forward.py → untouched (Global Constraints).
- §8 verification → py_compile in Task 4 Step 4; tests per task; commit per topic.
- §9 out of scope → walk_forward.py, sacred holdout, strategies/rydc.py, Wilder RMA all untouched.

**2. Placeholder scan:** All steps contain concrete code; no TBD/TODO/"similar to Task N".

**3. Type consistency:** `_atr_window(data, i, atr_period) -> tuple[list[float], list[float], list[float]]` used identically in Task 1 test and impl; `compute_features_lagged -> (X, y, price)` matches the pre-existing test contract; `compute_fold_pnl(..., price_level, min_confidence=0.85)` matches Task 4 test and caller.

**Spec deviations (documented):**
- Spec §4.3 references `smoke_rydc_sltp.py`, which does not exist in the repo — replaced with a unit test on the extracted `_atr_window` helper (Task 1).
- Spec §5.2 says `compute_features_lagged` returns `(X, y, target)`; the pre-existing RED test requires `(X, y, price)`. Plan follows the test contract and derives forward returns from `price` (`rets_full[t] = (price[t+1]-price[t])/price[t]`), which is numerically identical to `target[t]`.

## Execution Handoff

**"Plan complete and saved to `docs/superpowers/plans/2026-08-05-rydc-atr-alignment-pnl-honesty.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**