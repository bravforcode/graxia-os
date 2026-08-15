# Direction I — P4 Screening Wave 1 Acceptance Report (2026-08-06)

**Status:** COMPLETE — 80 shortlist candidates screened, 2 survivors (low bar: sharpe>0, trades≥30)
**Artifacts:** `research/catalog_i/screening_results_wave1.json`, `research/screening_log_i.json` (80 configs registered, +80 N)
**N accounting:** N_I = 1050 (baseline) + 80 screening configs + 0 trials = **1130** (for future DSR)

## Screening run

- Window: **2 years** (screening filter; trials use full history per governance)
- Costs: **conservative** — measured per-symbol profile + `cost_stress=True` (p95 spread), slippage measured or `no_slippage_data`
- Guard: TrackingGuard capture + `assert_no_guard_violations` (fail-closed) — **zero lookahead violations across all runs**
- Crash-safe: incremental results write + resume (survived 2 environment kills; resume completed 78-80)

## Status distribution (80)

| Status | Count | Meaning |
|---|---|---|
| no_strategy | 54 | `other` family — no engine strategy (honest skip, NOT forced) |
| no_slippage_data | 10 | measured spread/commission OK, slippage null in calibration (honest — P5 adds fill-simulator P90) |
| no_cost_data | 3 | no data/CSV for symbol×TF in duckdb/CSV |
| done | 13 | actually ran through the engine |
| VOID | 0 | zero guard violations, zero crashes after hardening |
| **survivors** | **2** | pass low bar |

## Survivors (P6 candidates after P5 re-filter at real costs)

| # | Candidate (catalog) | Family | Symbol/TF | Sharpe | Trades | PF | Return | MaxDD |
|---|---|---|---|---|---|---|---|---|
| 1 | Quantum XAUUSD Silver Trader | trend_following (Donchian) | XAUUSD D1 | **0.366** | 269 | 1.235 | +31.0% | 14.3% |
| 2 | naimkatiman/tradeclaw | regime (Donchian 50) | XAUUSD D1 | **0.391** | 172 | 1.367 | +26.2% | 8.2% |

Both are XAUUSD D1 slow trend/regime — consistent with the cost-viability analysis (XAUUSD 0.648bps RT is the only symbol that can carry retail-frequency trading; both survived conservative p95 costs). **Screening bar is LOW by design** — these are candidates, NOT verdicts; P5 re-filter at real (non-stress) costs + P6 full gate stack decide.

## Key engineering outcomes

1. **Engine bug found & worked around** (`reports/engine_equity_curve_bug_20260806.md`): Phase-4 pnl_tracker branch never appends equity_curve → sharpe/maxDD silently 0.0. Runner disables `_PHASE4_WIRING_AVAILABLE` → metrics real (verified sharpe 0.366 vs 0.0). Engine-side fix tracked; **P6 trials must apply the same workaround.**
2. **Guard enforcement real**: TrackingGuard capture proves zero lookahead per run (fail-closed if guard missing).
3. **54/80 `other`-family unmapped** — honest skip; P2 refinement (classify `other` bucket) would expand screening coverage in the next wave.
4. **Crash-safe pipeline**: 2 environment kills survived via incremental writes + resume.

## Next steps (per Plan 3.1)

- P5: calibrate remaining symbols (13 pending FROM_TICKS) + fill-simulator slippage P90 → unblock the 10 `no_slippage_data` candidates
- P5 re-filter of the 2 survivors at REAL costs (`--cost-mode base`) → P6 pre-registration candidates
- P2 refinement of `other` bucket → next screening wave
