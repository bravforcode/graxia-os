# M15 Scalper Post-Mortem (Trials 1034/1035) + Gross Diagnostic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a diagnostic-only gross (zero-cost) analysis layer to the M15 scalper benchmark, produce the gross artifact, write the formal post-mortem for REJECTED trials 1034/1035, and link it from the hypothesis registry.

**Architecture:** `gross_reconstruct()` re-adds recorded per-trade friction costs to net PnL (post-hoc, same trade set — mirrors the approved `cost_stress` pattern, no engine re-run), classifies each asset as `structural` (gross PF < 1.0) or `cost_driven` (gross PF ≥ 1.0, net PF < 1.0), and binary-searches the break-even cost multiplier. A `--include-gross` flag (default off) writes `reports/edge_search_m15_scalper_gross.json`. The verdict gates stay frozen — gross is diagnostic only.

**Tech Stack:** Python 3, pandas, numpy, argparse, BacktestEngine (unchanged), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-05-m15-scalper-post-mortem-design.md`

## Global Constraints

- **Engine trade schema (source of truth):** each trade dict has `pnl` (net, after all costs), `entry_spread_cost`, `entry_slippage_cost`, `exit_slippage_cost`, `fees` (all Decimal at engine level; floats after serialization). Fields named `net_pnl` / `total_cost` DO NOT exist — never use them.
- **Per-trade gross:** `gross_pnl = pnl + entry_spread_cost + entry_slippage_cost + exit_slippage_cost + fees`.
- **Classification:** `gross_pf < 1.0` → `structural` (break_even_mult = 0.0); `gross_pf >= 1.0` and net PF < 1.0 → `cost_driven`. No-loss gross → PF = inf → clamp `break_even_mult = 1.0`, `classification = cost_driven`. Empty trades → `no_trades`.
- **Break-even search:** binary search on multiplier `m ∈ [0, 1]`, 20 iterations, find the **maximum m with PF(m) >= 1**, where `sim_pnl(m) = gross_pnl − total_cost * m`.
- **measured_round_trip_bps:** `calibration["assets"][sym].get("round_trip_bps_measured", spread_bps_measured * 2)` — precedent `scripts/backtest_cost.py:396`; calibration file `config/cost_calibration.json` (v4.1).
- **Diagnostic only:** gates are NOT re-run; frozen core4 REJECT verdicts unchanged; gross is never a promotion path.
- **Frozen output:** default run (`python scripts/edge_search_m15_scalper.py`) produces identical core4 JSON — no schema change.
- **Git hygiene (MANDATORY):** use path-scoped commits only — `git commit -m "<msg>" -- <paths>` (bare `git commit` sweeps other agents' staged files; happened on 2026-08-05). Before each commit, run `git status --short` and confirm only intended files.
- **Registry footprint:** only entries 1034 and 1035 in `research/hypothesis_registry.json` — no other entries touched.
- Constants in runner: `INITIAL_CAPITAL = 10_000.0`, `MIN_DAILY_OBS = 30`, `ROOT = Path(__file__).resolve().parent.parent`.

## File Structure

- `scripts/edge_search_m15_scalper.py` — MODIFY: add `gross_reconstruct()`, `build_gross_artifact()`, `--include-gross` flag + wiring in `main()`.
- `tests/test_edge_search_m15_gross.py` — CREATE: unit tests for reconstruction, classification, break-even, edge cases, artifact builder.
- `reports/edge_search_m15_scalper_gross.json` — CREATE (by running the benchmark, Task 3): gross diagnostic artifact.
- `research/post_mortems/2026-08-05_m15_scalper_1034_1035.md` — CREATE: 8-section post-mortem (spec §5).
- `research/hypothesis_registry.json` — MODIFY: add `post_mortem` + `gross_artifact` keys to trials 1034/1035 only.

---

### Task 1: `gross_reconstruct()` + unit tests (TDD)

**Files:**
- Modify: `graxia/packages/quant_os/scripts/edge_search_m15_scalper.py` (add function after `cost_stress`, ~line 414)
- Create: `graxia/packages/quant_os/tests/test_edge_search_m15_gross.py`

**Interfaces:**
- Produces: `gross_reconstruct(asset_result: dict, measured_round_trip_bps: float) -> dict` returning:
  `{"n_trades", "gross_sharpe_daily", "gross_pf", "gross_win_pct", "gross_total_return_pct", "gross_monthly_pct", "net_sharpe_daily", "cost_erosion_sharpe", "break_even_mult", "break_even_round_trip_bps", "measured_round_trip_bps", "classification"}`. `asset_result` has keys `trades` (list of trade dicts with the engine schema), `first_bar`, `last_bar` (ISO strings). When no trades: `{"n_trades": 0, "gross_pf": 0.0, "classification": "no_trades"}`.
- Consumes: `pd`, `np`, `math`, `MIN_DAILY_OBS`, `INITIAL_CAPITAL` (already imported/defined in the runner module).

- [ ] **Step 1: Write the failing test file**

`graxia/packages/quant_os/tests/test_edge_search_m15_gross.py`:

```python
"""Tests for gross diagnostic reconstruction (post-mortem trials 1034/1035)."""

from __future__ import annotations

from graxia.packages.quant_os.scripts.edge_search_m15_scalper import (
    build_gross_artifact,
    gross_reconstruct,
)


def _trade(pnl, spread=0.0, eslip=0.0, xslip=0.0, fees=0.0, exit_time="2026-01-02T12:00:00Z"):
    return {
        "pnl": pnl,
        "entry_spread_cost": spread,
        "entry_slippage_cost": eslip,
        "exit_slippage_cost": xslip,
        "fees": fees,
        "exit_time": exit_time,
    }


def _asset_result(trades, first_bar="2026-01-01T00:00:00Z", last_bar="2026-02-01T00:00:00Z"):
    return {"trades": trades, "first_bar": first_bar, "last_bar": last_bar}


def test_gross_reconstruct_reconstruction_and_monotonicity():
    # Trade 1: net +5, costs 8 -> gross +13. Trade 2: net -12, costs 8 -> gross -4.
    # Net PF = 5/12 < 1; Gross PF = 13/4 > 1. Reconstruction turns the loss toward
    # breakeven, and gross_pf must always be >= net_pf.
    trades = [
        _trade(pnl=5.0, spread=4.0, eslip=2.0, xslip=2.0),
        _trade(pnl=-12.0, spread=4.0, eslip=2.0, xslip=2.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    assert res["gross_pf"] > 1.0
    assert res["classification"] == "cost_driven"
    assert res["gross_pf"] >= 5.0 / 12.0  # monotonicity: gross >= net
    assert res["n_trades"] == 2


def test_gross_reconstruct_break_even_mult():
    # sim_pnl(m) = gross - cost*m: (13-8m) / (4+8m) = 1 -> m = 0.5625
    trades = [
        _trade(pnl=5.0, spread=4.0, eslip=2.0, xslip=2.0),
        _trade(pnl=-12.0, spread=4.0, eslip=2.0, xslip=2.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    assert 0.0 < res["break_even_mult"] <= 1.0
    assert abs(res["break_even_mult"] - 0.5625) < 0.01
    assert abs(res["break_even_round_trip_bps"] - 15.0 * 0.5625) < 0.2


def test_gross_reconstruct_structural():
    # Both trades stay negative even after adding back costs: gross PF < 1.
    trades = [
        _trade(pnl=-10.0, spread=1.0, eslip=1.0, xslip=1.0),
        _trade(pnl=-15.0, spread=1.0, eslip=1.0, xslip=1.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    assert res["gross_pf"] < 1.0
    assert res["classification"] == "structural"
    assert res["break_even_mult"] == 0.0
    assert res["break_even_round_trip_bps"] == 0.0


def test_gross_reconstruct_no_losses_clamps_mult():
    # All gross positive -> PF = inf -> clamp break_even_mult at 1.0, cost_driven.
    trades = [
        _trade(pnl=2.0, spread=1.0),
        _trade(pnl=5.0, spread=1.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=10.0)
    assert res["classification"] == "cost_driven"
    assert res["break_even_mult"] == 1.0


def test_gross_reconstruct_empty_trades():
    res = gross_reconstruct(_asset_result([]), measured_round_trip_bps=15.0)
    assert res["classification"] == "no_trades"
    assert res["gross_pf"] == 0.0


def test_gross_reconstruct_costs_sharpe_keys_present():
    trades = [
        _trade(pnl=-2.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-02T12:00:00Z"),
        _trade(pnl=-3.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-03T12:00:00Z"),
        _trade(pnl=4.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-04T12:00:00Z"),
        _trade(pnl=6.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-05T12:00:00Z"),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    for key in ("gross_sharpe_daily", "net_sharpe_daily", "cost_erosion_sharpe",
                "gross_win_pct", "gross_total_return_pct", "gross_monthly_pct",
                "measured_round_trip_bps"):
        assert key in res


def test_build_gross_artifact_schema():
    trades = [
        _trade(pnl=-10.0, spread=1.0, eslip=1.0, xslip=1.0),
        _trade(pnl=-15.0, spread=1.0, eslip=1.0, xslip=1.0),
    ]
    ar = {"symbol": "XAUUSD", **{"trades": trades, "first_bar": "2026-01-01T00:00:00Z",
                                  "last_bar": "2026-02-01T00:00:00Z"}}
    art = build_gross_artifact([ar], {"XAUUSD": 15.0})
    assert art["meta"]["diagnostic_only"] is True
    assert art["meta"]["verdict_unchanged"] is True
    assert art["per_asset"]["XAUUSD"]["classification"] == "structural"
    assert art["break_even"]["XAUUSD"]["measured_round_trip_bps"] == 15.0
    assert art["summary"]["n_assets"] == 1
    assert art["summary"]["n_structural"] == 1
    assert art["summary"]["n_cost_driven"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest graxia/packages/quant_os/tests/test_edge_search_m15_gross.py -q --tb=short`
Expected: FAIL with `ImportError: cannot import name 'gross_reconstruct'`.

- [ ] **Step 3: Implement `gross_reconstruct()` and `build_gross_artifact()`**

Insert after `cost_stress` (after line ~414) in `graxia/packages/quant_os/scripts/edge_search_m15_scalper.py`:

```python
def gross_reconstruct(asset_result: dict, measured_round_trip_bps: float) -> dict:
    """Post-hoc gross (zero-cost) reconstruction — DIAGNOSTIC ONLY.

    Re-adds recorded friction costs to net PnL on the SAME trade set
    (mirrors cost_stress; no engine re-run). Classifies the asset as
    'structural' (gross PF < 1.0 — no edge even free) or 'cost_driven'
    (gross PF >= 1.0 but net PF < 1.0 — friction consumed the edge) and
    binary-searches the break-even cost multiplier m: the maximum
    m in [0, 1] with PF(m) >= 1 where sim_pnl(m) = gross_pnl - total_cost * m.
    Never alters the frozen gate verdicts.
    """
    trades = asset_result["trades"]
    if not trades:
        return {"n_trades": 0, "gross_pf": 0.0, "classification": "no_trades"}

    gross_pnls = []
    cost_totals = []
    for t in trades:
        cost = (
            float(t.get("entry_spread_cost", 0.0))
            + float(t.get("entry_slippage_cost", 0.0))
            + float(t.get("exit_slippage_cost", 0.0))
            + float(t.get("fees", 0.0))
        )
        cost_totals.append(cost)
        gross_pnls.append(float(t["pnl"]) + cost)

    def pf_of(pnls):
        wins = sum(p for p in pnls if p > 0)
        losses = abs(sum(p for p in pnls if p < 0))
        if losses <= 0:
            return float("inf")
        return wins / losses

    net_pf = pf_of([float(t["pnl"]) for t in trades])
    gross_pf = pf_of(gross_pnls)

    # --- equity -> daily returns for Sharpe (cost_stress aggregation path) ---
    srt = sorted(
        ((pd.Timestamp(t["exit_time"], tz="UTC"), p) for t, p in zip(trades, gross_pnls)),
        key=lambda x: x[0],
    )
    eq = INITIAL_CAPITAL
    points = []
    for ts, pnl in srt:
        eq += pnl
        points.append((ts, eq))
    df = pd.DataFrame(points, columns=["ts", "eq"])
    df["day"] = df["ts"].dt.date
    daily = df.groupby("day")["eq"].last()
    rets = daily.pct_change().dropna()
    n_days = len(rets)
    mu = float(rets.mean()) if n_days else 0.0
    sd = float(rets.std(ddof=1)) if n_days > 1 else 0.0
    gross_sharpe = mu / (sd + 1e-10) * math.sqrt(252) if n_days else 0.0

    net_pnls = [float(t["pnl"]) for t in trades]
    net_mu = float(pd.Series(net_pnls).mean())
    # net sharpe on the same daily aggregation for a comparable erosion figure
    srt_net = sorted(
        ((pd.Timestamp(t["exit_time"], tz="UTC"), p) for t, p in zip(trades, net_pnls)),
        key=lambda x: x[0],
    )
    eq_net = INITIAL_CAPITAL
    points_net = []
    for ts, pnl in srt_net:
        eq_net += pnl
        points_net.append((ts, eq_net))
    dfn = pd.DataFrame(points_net, columns=["ts", "eq"])
    dfn["day"] = dfn["ts"].dt.date
    daily_net = dfn.groupby("day")["eq"].last()
    rets_net = daily_net.pct_change().dropna()
    n_days_net = len(rets_net)
    mu_net = float(rets_net.mean()) if n_days_net else 0.0
    sd_net = float(rets_net.std(ddof=1)) if n_days_net > 1 else 0.0
    net_sharpe = mu_net / (sd_net + 1e-10) * math.sqrt(252) if n_days_net else 0.0

    wins = [p for p in gross_pnls if p > 0]
    losses = [p for p in gross_pnls if p < 0]
    gross_win_pct = len(wins) / len(gross_pnls) * 100.0 if gross_pnls else 0.0

    first_eq = INITIAL_CAPITAL
    last_eq = INITIAL_CAPITAL + sum(gross_pnls)
    total_return_pct = (last_eq / first_eq - 1.0) * 100.0 if first_eq else 0.0
    t0 = pd.Timestamp(asset_result["first_bar"], tz="UTC")
    t1 = pd.Timestamp(asset_result["last_bar"], tz="UTC")
    span_days = max((t1 - t0).days, 1)
    monthly_pct = total_return_pct / (span_days / 30.44)

    # --- break-even binary search on multiplier m in [0, 1] ---
    if gross_pf < 1.0:
        be_mult = 0.0
        classification = "structural"
    else:
        classification = "cost_driven"
        low, high = 0.0, 1.0
        be_mult = 1.0 if net_pf >= 1.0 else 0.0
        if net_pf < 1.0:
            for _ in range(20):
                mid = (low + high) / 2.0
                sim = [g - c * mid for g, c in zip(gross_pnls, cost_totals)]
                if pf_of(sim) >= 1.0:
                    be_mult = mid
                    low = mid
                else:
                    high = mid

    return {
        "n_trades": len(trades),
        "gross_sharpe_daily": round(gross_sharpe, 4),
        "gross_pf": round(gross_pf, 4) if gross_pf < 100.0 else 99.99,
        "gross_win_pct": round(gross_win_pct, 2),
        "gross_total_return_pct": round(total_return_pct, 2),
        "gross_monthly_pct": round(monthly_pct, 3),
        "net_sharpe_daily": round(net_sharpe, 4),
        "cost_erosion_sharpe": round(net_sharpe - gross_sharpe, 4),
        "break_even_mult": round(be_mult, 4),
        "break_even_round_trip_bps": round(measured_round_trip_bps * be_mult, 2),
        "measured_round_trip_bps": round(measured_round_trip_bps, 2),
        "classification": classification,
    }


def build_gross_artifact(asset_results: list[dict], measured_bps_map: dict[str, float]) -> dict:
    """Assemble the diagnostic-only gross artifact (spec §4 schema)."""
    per_asset = {}
    break_even = {}
    n_cost = 0
    n_struct = 0
    for ar in asset_results:
        sym = ar["symbol"]
        bps = measured_bps_map.get(sym, 0.0)
        g = gross_reconstruct(ar, bps)
        per_asset[sym] = g
        break_even[sym] = {
            "break_even_mult": g["break_even_mult"],
            "break_even_round_trip_bps": g["break_even_round_trip_bps"],
            "measured_round_trip_bps": g["measured_round_trip_bps"],
            "classification": g["classification"],
        }
        if g["classification"] == "cost_driven":
            n_cost += 1
        elif g["classification"] == "structural":
            n_struct += 1
    return {
        "meta": {
            "method": "post-hoc cost reconstruction (mult=0.0), same trade set",
            "source": "edge_search_m15_scalper_core4.json",
            "generated": datetime.now(UTC).isoformat(),
            "diagnostic_only": True,
            "verdict_unchanged": True,
        },
        "per_asset": per_asset,
        "break_even": break_even,
        "summary": {"n_assets": len(asset_results), "n_cost_driven": n_cost, "n_structural": n_struct},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest graxia/packages/quant_os/tests/test_edge_search_m15_gross.py -q --tb=short`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit (path-scoped)**

```bash
git add graxia/packages/quant_os/scripts/edge_search_m15_scalper.py graxia/packages/quant_os/tests/test_edge_search_m15_gross.py
git status --short   # confirm ONLY these two files staged
git commit -m "feat(quant_os): add gross reconstruction diagnostic to M15 scalper runner" -- graxia/packages/quant_os/scripts/edge_search_m15_scalper.py graxia/packages/quant_os/tests/test_edge_search_m15_gross.py
```

---

### Task 2: Wire `--include-gross` flag + artifact write in `main()`

**Files:**
- Modify: `graxia/packages/quant_os/scripts/edge_search_m15_scalper.py` (argparse block ~line 463-470; artifact write ~line 657-660)

**Interfaces:**
- Consumes: `build_gross_artifact` (Task 1), `ROOT`, `json`, `datetime` (already imported).
- Produces: CLI flag `--include-gross`; when set, writes `reports/edge_search_m15_scalper_gross.json` (or `--gross-out` override).

- [ ] **Step 1: Add the flag**

In `main()`, after the `--label-shuffle` argument (line ~469):

```python
    parser.add_argument("--include-gross", action="store_true", default=False,
                        help="write diagnostic gross (zero-cost) artifact — does NOT change verdicts")
    parser.add_argument("--gross-out", default="reports/edge_search_m15_scalper_gross.json",
                        help="output path for the gross diagnostic artifact")
```

- [ ] **Step 2: Add measured-bps loading + artifact write before the final output**

Before the final `out = ROOT / args.out` block (~line 657), insert:

```python
    if args.include_gross:
        print("\nGross diagnostic (DIAGNOSTIC ONLY — verdicts frozen):")
        calib = json.loads((ROOT / "config" / "cost_calibration.json").read_text(encoding="utf-8"))
        calib_assets = calib.get("assets", {})
        measured_bps = {}
        for sym in assets:
            entry = calib_assets.get(sym, {})
            spread = float(entry.get("spread_bps_measured", 0.0))
            bps = float(entry.get("round_trip_bps_measured", spread * 2.0))
            measured_bps[sym] = bps
            print(f"  {sym}: measured_round_trip_bps={bps:.2f}")
        gross_artifact = build_gross_artifact(asset_results, measured_bps)
        for sym, g in gross_artifact["per_asset"].items():
            print(f"  {sym}: gross_PF={g['gross_pf']} net_sharpe={g['net_sharpe_daily']} "
                  f"gross_sharpe={g['gross_sharpe_daily']} break_even_mult={g['break_even_mult']} "
                  f"classification={g['classification']}")
        gross_out = ROOT / args.gross_out
        gross_out.parent.mkdir(parents=True, exist_ok=True)
        gross_out.write_text(json.dumps(gross_artifact, indent=2, default=str), encoding="utf-8")
        print(f"Gross artifact written: {gross_out}")
```

- [ ] **Step 3: Verify no regression on the default path**

Run: `python -m pytest graxia/packages/quant_os/tests/test_edge_search_m15_gross.py -q --tb=short`
Expected: PASS (8 tests — flag addition does not affect them).

Run a syntax/import check without executing the full benchmark:
`python -c "import graxia.packages.quant_os.scripts.edge_search_m15_scalper as m; print('imports OK', hasattr(m, 'main'))"`
Expected: `imports OK True`

- [ ] **Step 4: Commit (path-scoped)**

```bash
git add graxia/packages/quant_os/scripts/edge_search_m15_scalper.py
git status --short   # confirm ONLY this file
git commit -m "feat(quant_os): wire --include-gross diagnostic flag and gross artifact" -- graxia/packages/quant_os/scripts/edge_search_m15_scalper.py
```

---

### Task 3: Run benchmark with `--include-gross` → produce gross artifact

**Files:**
- Create: `graxia/packages/quant_os/reports/edge_search_m15_scalper_gross.json` (generated)

**Interfaces:**
- Consumes: `python scripts/edge_search_m15_scalper.py --include-gross` (Tasks 1+2).

- [ ] **Step 1: Run the benchmark with the flag**

Run from monorepo root (`C:\Users\menum\graxia os`):
`python graxia/packages/quant_os/scripts/edge_search_m15_scalper.py --include-gross`
Expected: preflight passes for XAUUSD/USDJPY/EURUSD/GBPUSD, benchmark completes, gross artifact written to `graxia/packages/quant_os/reports/edge_search_m15_scalper_gross.json`.

- [ ] **Step 2: Validate the artifact**

```python
python -c "
import json
d = json.load(open(r'graxia/packages/quant_os/reports/edge_search_m15_scalper_gross.json', encoding='utf-8'))
assert d['meta']['diagnostic_only'] is True and d['meta']['verdict_unchanged'] is True
assert set(d['per_asset'].keys()) == {'XAUUSD', 'USDJPY', 'EURUSD', 'GBPUSD'}
for sym, g in d['per_asset'].items():
    assert g['classification'] in ('structural', 'cost_driven')
    assert g['measured_round_trip_bps'] > 0
    assert g['break_even_mult'] >= 0.0 and g['break_even_mult'] <= 1.0
print('OK', d['summary'])
"
```

Expected: `OK {'n_assets': 4, 'n_cost_driven': ..., 'n_structural': ...}` with no assertion errors. Sanity: any asset with `gross_pf >= 1.0` must be `cost_driven`; `gross_pf < 1.0` must be `structural` (cross-check against `edge_search_m15_scalper_core4.json` net PF values).

- [ ] **Step 3: Full unit-test regression**

Run: `python -m pytest graxia/packages/quant_os/tests/test_edge_search_m15_gross.py graxia/packages/quant_os/tests/test_happy_gold_scalper.py graxia/packages/quant_os/tests/test_asian_scalper.py -q --tb=short`
Expected: PASS (8 + 9 + 10 = 27 tests; adjust counts to actual).

- [ ] **Step 4: Commit (path-scoped)**

```bash
git add graxia/packages/quant_os/reports/edge_search_m15_scalper_gross.json
git status --short   # confirm ONLY this file
git commit -m "reports(quant_os): M15 scalper gross diagnostic artifact (trials 1034/1035)" -- graxia/packages/quant_os/reports/edge_search_m15_scalper_gross.json
```

---

### Task 4: Post-mortem document + registry update

**Files:**
- Create: `graxia/packages/quant_os/research/post_mortems/2026-08-05_m15_scalper_1034_1035.md`
- Modify: `graxia/packages/quant_os/research/hypothesis_registry.json` (entries 1034/1035 only)

**Interfaces:**
- Consumes: `reports/edge_search_m15_scalper_core4.json`, `reports/edge_search_m15_scalper_gross.json` (Task 3), `research/hypothesis_registry.json`, `config/cost_calibration.json`.

- [ ] **Step 1: Read the actual gross numbers**

```python
python -c "
import json
d = json.load(open(r'graxia/packages/quant_os/reports/edge_search_m15_scalper_gross.json', encoding='utf-8'))
for sym, g in d['per_asset'].items():
    print(sym, '| gross_pf', g['gross_pf'], '| gross_sharpe', g['gross_sharpe_daily'],
          '| net_sharpe', g['net_sharpe_daily'], '| be_mult', g['break_even_mult'],
          '| be_bps', g['break_even_round_trip_bps'], '|', g['classification'])
print('SUMMARY', d['summary'])
"
```

Record the numbers — they fill the evidence tables below verbatim (no invented values).

- [ ] **Step 2: Write the post-mortem document**

Create `graxia/packages/quant_os/research/post_mortems/2026-08-05_m15_scalper_1034_1035.md` with the 8-section template from spec §5, using the REAL numbers from Step 1:

```markdown
# M15 Scalper Post-Mortem — Trials 1034 (Happy Gold Scalper) & 1035 (Asian Scalper)

- **Verdicts:** 1034 REJECTED, 1035 REJECTED (gates 2/7) — frozen, unchanged
- **Pre-registrations:** research/pre_registration/trial_1034_happy_gold_scalper.md,
  research/pre_registration/trial_1035_asian_scalper.md
- **Evidence:** reports/edge_search_m15_scalper_core4.json (net),
  reports/edge_search_m15_scalper_gross.json (diagnostic gross)
- **Costs:** config/cost_calibration.json (v4.1)

## 1. Executive Summary

[verdict box — per-trial classification from the gross artifact; one-paragraph
decision on the M15 scalper class]

## 2. Evidence

| Asset | Trial | n_trades | Net Sharpe | Net PF | Gross Sharpe | Gross PF | Win% | Monthly% |
|-------|-------|----------|-----------|--------|--------------|----------|------|----------|
| XAUUSD | 1034 | 2432 | -0.62 | 0.95 | <actual> | <actual> | 43.9 | -1.78 |
| USDJPY | 1035 | 895 | -4.73 | 0.68 | <actual> | <actual> | 45.3 | -3.08 |
| EURUSD | 1035 | 401 | -2.61 | 0.85 | <actual> | <actual> | 49.4 | -2.39 |
| GBPUSD | 1035 | 371 | -1.78 | 0.94 | <actual> | <actual> | — | -1.75 |

[replace <actual> with Step-1 values; pooled: 1035 DSR p=1.0, Deflated-Kelly t=-1.51]

## 3. Failure-Mode Analysis

[1034: gross vs net PF — did friction consume the edge? quote break_even_round_trip_bps
vs measured bps. 1035: gross PF per pair — structural fade-the-range failure; DSR p=1.0]

## 4. Break-Even Table

[per asset: break_even_mult, break_even_round_trip_bps, measured_round_trip_bps, classification]

## 5. Lessons Learned

[thresholds derived from ACTUAL numbers — e.g. gross PF required for survival at
measured costs; what to check before pre-registering the next M15 scalper]

## 6. Decision

[go / no-go on M15 scalper class + explicit criteria if go]

## 7. References

[all artifacts + registry entries]
```

**No placeholder values may survive:** every `<actual>` must be replaced by the Step-1 number before commit. If gross data is missing for an asset (e.g., no trades), say so explicitly with `no_trades`.

- [ ] **Step 3: Update the registry (only 1034/1035)**

Edit `graxia/packages/quant_os/research/hypothesis_registry.json`: in the hypothesis entries with `"trial_number": 1034` and `"trial_number": 1035`, add exactly:

```json
"post_mortem": "research/post_mortems/2026-08-05_m15_scalper_1034_1035.md",
"gross_artifact": "reports/edge_search_m15_scalper_gross.json"
```

Verify only those two entries changed:
`git diff graxia/packages/quant_os/research/hypothesis_registry.json` — hunk must touch ONLY trial 1034/1035 blocks (check with python: parse JSON, assert only those two entries gained the keys).

- [ ] **Step 4: Commit both files (path-scoped)**

```bash
git add graxia/packages/quant_os/research/post_mortems/2026-08-05_m15_scalper_1034_1035.md graxia/packages/quant_os/research/hypothesis_registry.json
git status --short   # confirm ONLY these two files
git commit -m "docs(quant_os): M15 scalper post-mortem trials 1034/1035" -- graxia/packages/quant_os/research/post_mortems/2026-08-05_m15_scalper_1034_1035.md graxia/packages/quant_os/research/hypothesis_registry.json
```

---

## Self-Review (run after writing — fixed inline)

1. **Spec coverage:** §2 deliverables → Tasks 1/2 (runner), Task 3 (artifact), Task 4 (doc + registry). §3 flag/classification/edge cases → Task 1 tests + implementation. §4 artifact schema → `build_gross_artifact` + Task 3 validation. §5 doc template → Task 4 Step 2. §6 registry → Task 4 Step 3. §7 testing → Task 1 Steps 1-4 + Task 3 Step 3. §8 out of scope → no tasks reference Extended Fix 3/Fix 1. §9 commits → per-task path-scoped commits. Covered.
2. **Placeholder scan:** the only `<actual>` markers are inside Task 4 Step 2's template with an explicit "no placeholder values may survive" gate — they are filled from Task 3's artifact, not invented. All other code blocks are complete.
3. **Type consistency:** `gross_reconstruct(asset_result, measured_round_trip_bps)` signature used identically in tests, implementation, `build_gross_artifact`, and main wiring; return keys consistent across Task 1, artifact builder, and Task 4 table columns. `measured_bps_map` (dict[str, float]) used in both `build_gross_artifact` signature and Task 2 wiring. Consistent.
