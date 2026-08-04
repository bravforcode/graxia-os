# Design Spec — M15 Scalper Post-Mortem (Trials 1034/1035) + Gross Diagnostic

- **Date:** 2026-08-05
- **Status:** Approved (design review)
- **Owner:** quant_os EA-BENCH workstream
- **Branch:** feat/execution-risk-clean
- **Pre-registrations:** `research/pre_registration/trial_1034_happy_gold_scalper.md`, `research/pre_registration/trial_1035_asian_scalper.md`
- **Source evidence:** `reports/edge_search_m15_scalper_core4.json` (REJECT verdicts, gates 2/7)

## 1. Purpose

Produce a formal post-mortem for M15 scalper trials 1034 (Happy Gold Scalper, XAUUSD) and
1035 (Asian Scalper, EURUSD/GBPUSD/USDJPY), both REJECTED by the EA-BENCH gate stack
(pooled DSR p=1.0 for 1035; all-negative net Sharpe and PF 0.68–0.95 across assets).

The post-mortem serves two goals (user-approved):

1. **Decision gate** — go/no-go recommendation for the M15 scalper strategy class.
2. **Knowledge base** — lessons learned feeding future pre-registrations (thresholds,
   failure modes, cost ceilings).

Core question answered per trial: **cost-driven death** (signal edge exists but friction
consumes it) vs **structural death** (no edge even at zero cost).

## 2. Deliverables

| # | Deliverable | Location |
|---|-------------|----------|
| 1 | `--include-gross` flag + `gross_reconstruct()` in benchmark runner | `scripts/edge_search_m15_scalper.py` |
| 2 | Gross diagnostic artifact | `reports/edge_search_m15_scalper_gross.json` |
| 3 | Post-mortem document (8-section template) | `research/post_mortems/2026-08-05_m15_scalper_1034_1035.md` |
| 4 | Registry links on trials 1034/1035 only | `research/hypothesis_registry.json` |

## 3. Runner change — `--include-gross` (diagnostic only)

### 3.1 Flag semantics

- New CLI flag `--include-gross` (store_true, **default off**).
- Default run output (`edge_search_m15_scalper_core4.json`) is **unchanged** — backward
  compatible; no schema change to the frozen core4 report.
- When enabled, the runner computes gross diagnostics **from trades held in memory**
  during the same benchmark run (the core4 report does not persist raw trades, so the
  gross artifact is produced from the same run, not from a separate engine pass).

### 3.2 `gross_reconstruct(asset_results, measured_cost_bps)` — post-hoc reconstruction

Method: for each trade, re-add all recorded friction costs to net PnL, then rebuild
equity (capital + cumulative realized pnl; max_positions=1 scalper path — same documented
approximation as `cost_stress`).

**Engine trade schema (source of truth — same fields consumed by approved `cost_stress`):**

```
t["pnl"]                      net realized PnL (after all costs)
t["entry_spread_cost"]        spread cost at entry
t["entry_slippage_cost"]      slippage cost at entry
t["exit_slippage_cost"]       slippage cost at exit
t["fees"]                     commission / fees
```

Per-trade: `gross_pnl = pnl + entry_spread_cost + entry_slippage_cost + exit_slippage_cost + fees`
(equivalently `gross_pnl = pnl + total_cost` where `total_cost` is the sum of the four cost
fields). NOTE: the reviewer's code sketch referenced fields `net_pnl` / `total_cost`; the
engine does not emit those names — implementation standardizes on the schema above.

Outputs per asset:

- `gross_sharpe_daily`, `gross_pf`, `gross_win_pct`, `gross_total_return_pct`,
  `gross_monthly_pct` (mirror keys of the net per-asset metrics for direct comparison)
- `net_sharpe_daily` (carried over), `cost_erosion_sharpe = net_sharpe_daily − gross_sharpe_daily`
- `n_trades`

### 3.3 Automatic classification + break-even

- `gross_pf < 1.0` → **`structural`** (no cost level saves it; break-even mult = 0.0).
- `gross_pf >= 1.0` and net PF < 1.0 → **`cost_driven`**; binary search on multiplier
  `m ∈ [0, 1]` (20 iterations) finds the **maximum m with PF(m) >= 1**, where
  `sim_pnl(m) = gross_pnl − total_cost * m`.
  - `break_even_mult = m`
  - `break_even_round_trip_bps = measured_round_trip_bps * m`
  - `measured_round_trip_bps` = the symbol's measured **round-trip** cost per trade
    (spread + commission) in bps, matching what the core4 run charged. Sourced from
    `config/cost_calibration.json` (v4.1) via `SymbolCostProfile` (same path as
    `preflight_costs`); the exact profile attribute is resolved at implementation time
    and cross-checked against the trade-level cost fields from §3.2
    (mean `total_cost` / mean notional) so the bps denominator matches the core4 run.
- Edge cases: empty trade list → `no_trades`; no gross losses → PF = inf, clamp
  `break_even_mult = 1.0` with `classification = cost_driven` and note in artifact.
- Monotonicity guarantee: `sim_pnl` strictly decreases in `m`, so PF is non-increasing
  in `m`; binary search is valid. Property `gross_pf >= net_pf` always holds.

### 3.4 Governance invariant

Gross diagnostics are **diagnostic only**:

- Gates are NOT re-run; the frozen core4 REJECT verdicts are unchanged.
- Gross metrics are not a promotion path and never override a net-based REJECT.
- Artifact carries `"diagnostic_only": true`, `"verdict_unchanged": true`.

## 4. Gross artifact — `reports/edge_search_m15_scalper_gross.json`

```json
{
  "meta": {
    "method": "post-hoc cost reconstruction (mult=0.0), same trade set",
    "source": "edge_search_m15_scalper_core4.json",
    "generated": "<ISO-8601>",
    "diagnostic_only": true,
    "verdict_unchanged": true
  },
  "per_asset": {
    "XAUUSD": {
      "n_trades": 2432,
      "gross_sharpe_daily": 0.0,
      "gross_pf": 0.0,
      "gross_win_pct": 0.0,
      "gross_total_return_pct": 0.0,
      "gross_monthly_pct": 0.0,
      "net_sharpe_daily": -0.6167,
      "cost_erosion_sharpe": 0.0
    }
  },
  "break_even": {
    "XAUUSD": {
      "break_even_mult": 0.0,
      "break_even_round_trip_bps": 0.0,
      "measured_round_trip_bps": 0.0,
      "classification": "structural|cost_driven"
    }
  },
  "summary": { "n_assets": 4, "n_cost_driven": 0, "n_structural": 0 }
}
```

## 5. Post-mortem document — `research/post_mortems/2026-08-05_m15_scalper_1034_1035.md`

Eight-section template:

1. **Meta header** — trials, verdicts (REJECTED, 2/7 gates), links: pre-reg docs, core4
   report, gross artifact, cost_calibration v4.1.
2. **Executive summary** — verdict box: classification per trial (cost_driven /
   structural / mixed) + decision on the M15 scalper class.
3. **Evidence tables** — per asset: net vs gross (Sharpe, PF, win%, monthly%, n_trades,
   cost_erosion_sharpe); pooled DSR p (1035: p=1.0).
4. **Failure-mode analysis** — 1034 XAUUSD: gross PF vs net PF, break-even bps vs
   measured v4.1 bps (how much of the edge friction consumed). 1035 FX 3 pairs: gross PF
   per pair + DSR p=1.0 → fade-the-range thesis fails structurally (gross does not
   survive either).
5. **Break-even table** — per asset: break_even_mult, break_even_round_trip_bps,
   measured_round_trip_bps, classification.
6. **Lessons learned** — knowledge-base entries for future pre-registration (e.g., an
   M15 FX scalper on 7 bps commission requires gross PF >= ~1.15 before net can survive —
   threshold derived from actual data in this post-mortem, not assumed).
7. **Decision** — go/no-go on the M15 scalper class + explicit criteria if "go" (what a
   next trial must satisfy).
8. **References** — all artifacts, registry entries, calibration file.

## 6. Registry update — `research/hypothesis_registry.json`

Add exactly two keys to entries **1034 and 1035 only** (no other entries touched):

```json
"post_mortem": "research/post_mortems/2026-08-05_m15_scalper_1034_1035.md",
"gross_artifact": "reports/edge_search_m15_scalper_gross.json"
```

## 7. Testing & verification

New unit test file `tests/test_edge_search_m15_gross.py` (synthetic trades using the
engine schema from §3.2):

1. **Reconstruction** — `gross_pnl == pnl + Σ costs` per trade.
2. **Monotonicity** — `gross_pf >= net_pf` always.
3. **cost_driven classification** — synthetic trades with gross PF > 1 but net PF < 1 →
   `classification == "cost_driven"`, `0 < break_even_mult <= 1`.
4. **structural classification** — all-gross-negative trades →
   `classification == "structural"`, `break_even_mult == 0.0`.
5. **Empty trades** — `classification == "no_trades"`, `gross_pf == 0.0`.

Live verification:

- `python scripts/edge_search_m15_scalper.py --include-gross` → artifact
  `reports/edge_search_m15_scalper_gross.json` with complete per-asset values and
  classifications consistent with PF math.
- Full `tests/` regression run (no regression to core4 gates — gates untouched).
- **Gates are NOT re-run; verdicts stay frozen.**

## 8. Explicitly out of scope

- **Extended Fix 3**: hardcoded prices (e.g., $2350.0) in 3 remaining research scripts.
- **Extended Fix 1**: `_run_pbo` in `backtest/runner.py`.
- These are a separate validation-stack workstream and will be registered as follow-up
  tasks AFTER this post-mortem lands.

## 9. Commit plan

1. `docs: add design spec for M15 scalper post-mortem and gross artifact diagnostic`
   (this file)
2. `feat(quant_os): add --include-gross diagnostic to M15 scalper runner`
   (runner + unit tests)
3. `reports(quant_os): M15 scalper gross diagnostic artifact (trials 1034/1035)`
   (artifact JSON)
4. `docs(quant_os): M15 scalper post-mortem trials 1034/1035`
   (post-mortem markdown + registry update)
