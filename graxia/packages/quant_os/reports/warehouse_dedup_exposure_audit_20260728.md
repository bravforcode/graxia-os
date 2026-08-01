# Warehouse Dedup Bug — Historical Trial Exposure Audit

Date: 2026-07-28
Generated: manual audit (Claude Code), cross-referenced against actual runner
scripts, not assumed from trial IDs.

## Background

`data/warehouse_loader.py::Warehouse.get_ohlcv()` has a confirmed real-data
bug: overlapping hive-partitioned parquet files cause every bar to be
returned exactly 6x (byte-identical rows) — XAUUSD/H1 returned 300,000 raw
rows for only 50,000 unique timestamps. Duplicate rows are not independent
observations; if a walk-forward test's DK/t-statistic was computed on
undeduplicated data, its denominator (standard error) is artificially
shrunk, inflating the apparent significance of whatever mean return the data
shows — in either direction.

A defensive dedup (`_dedupe_warehouse_ohlcv`) was added inside
`backtest/data_loader.py::_load_ohlcv_warehouse` in commit `abf27f06`
(confirmed via `git log -S"_dedupe_warehouse_ohlcv"`), one of the last few
commits on this branch. Tests pinning the fix: `tests/test_warehouse_dedup.py`.

## Question

Which already-completed research trials in the ledgers ran through the
buggy pre-fix warehouse path, vs. a different, unaffected loader?

## Findings

| Trial(s) | Loader actually used | Exposure |
|---|---|---|
| RYDC-ARM-A (1001) | `csv.DictReader` on `data/rydc/rydc_daily.csv` (`scripts/run_rydc_validation.py`) | NOT AFFECTED |
| gold_ict_batch (1009-1021) | `pd.read_csv` on `data/XAUUSD_D1.csv` (`scripts/edge_search_gold_ict.py` + siblings) | NOT AFFECTED |
| PATHB-CARRY/VRP/CAM/COT-XAUUSD (2001-2003, 2007) | `pd.read_csv`/`pd.read_parquet` (`scripts/edge_search_all.py`) | NOT AFFECTED |
| PATHB-DXY-DIV, PATHB-TSMOM (2004, 2005) | Same (`edge_search_all.py`, via `scripts/rerun_3004_3005.py` for the 100k rerun) | NOT AFFECTED |
| PATHB-FOMC (2006) | Same (`edge_search_all.py`) | NOT AFFECTED |
| PATHB-CARRY-FX (2008 / "3008") | Never executed — blocked on missing EUR/JPY rate data | NOT AFFECTED (no run occurred) |
| Pooled 17-strategy DK-test (EDGE_SEARCH_FINAL_20260718.md) | `pd.read_csv`/`pd.read_parquet` directly (`scripts/edge_search_all.py`) | NOT AFFECTED |
| 2B.5b XAUUSD TripleBoostEnsemble retrain (DSR -0.78, NO-GO) | `_load_ohlcv_duckdb` — `RETRAIN_DATA_SOURCE = "duckdb"` hardcoded in `scripts/auto_retrain.py:74`, **specifically because of this bug** (see comment at lines 65-73, verified verbatim) | NOT AFFECTED — deliberately routed around |
| FOREX_EDGE_INVESTIGATION.md (GBPUSD/USDJPY/USDCAD/USDCHF/AUDUSD/NZDUSD) | Doc cites "Engine: `validation/walk_forward.py`" but the invoking script/config could not be located | **UNKNOWN** |

## Verdict

Every trial we could trace a runner for used a loader (CSV, parquet,
DuckDB) unaffected by the warehouse bug. The 2B.5b retrain's NO-GO
verdict is confirmed clean — the codebase's own comment shows the bug
was found and routed around *before* that retrain ran, not after.

**The one open gap:** the 6 FOREX_EDGE_INVESTIGATION.md trials (2
REJECT + 4 INCONCLUSIVE/underpowered) — could not confirm which loader
produced them. Their conclusions do not currently need to be
retracted, but should not be cited as "clean" until the actual
runner is found. Action: locate the script that produced
FOREX_EDGE_INVESTIGATION.md before those 6 trials are used as evidence
in any future gate decision.

**Conclusion:** the previously-flagged risk ("warehouse dedup may have
inflated historical p-values across the trial ledger") does not
materialize in practice — the trial-generating scripts never routed
through the warehouse loader in the first place, whether by original
design (CSV-based `edge_search_all.py`) or by deliberate avoidance
(`auto_retrain.py`'s explicit `source="duckdb"` choice). This item is
resolved, except for the FOREX_EDGE_INVESTIGATION.md loader
provenance, which remains open.

## Related finding surfaced during this audit (separate from dedup, logged here for traceability)

Two *positive* "GO"-verdict result files exist outside every trial ledger,
never counted toward N, never BH-corrected:
`reports/pooled_donchianp1_results.json` (dk_t=+7.93, 2026-07-19) and
`reports/pooled_tsmdxydivergence_results.json` (dk_t=+4.95, 2026-07-19).
Both results are driven almost entirely by EURUSD/GBPUSD legs with the same
high-profit-factor / high-max-drawdown signature `EDGE_SEARCH_FINAL_20260718.md`
elsewhere flags as a likely tick-size/pip-scaling artifact, while the XAUUSD
leg in each is flat. See `scripts/check_strategy_against_ledger.py`'s
`UNGATED_POSITIVE` entries for `strategies/donchian_p1.py` and
`strategies/tsm_dxy_divergence.py` for the full reasoning. These need a
unit-scaling bug check before any registration decision, and a real ledger
entry either way.
