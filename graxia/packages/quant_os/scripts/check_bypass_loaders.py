#!/usr/bin/env python3
"""
Chokepoint-bypass guard.

BacktestEngine (core/lookahead_guard.py) and provenance.py
(load_provenance_checked / require_cost_calibrated) are the project's two
data/execution chokepoints. Trial #1030's validator
(scripts/validate_dtsmom_strategy.py) defined its own load_data() and never
imported either -- it skipped the LookaheadGuard pre-flight scan AND the
cost-calibration gate entirely, and independently fabricated a flat cost
assumption in the process. That specific script is not unique: this scanner
found 33 other files with the same shape at the time it was written
(2026-07-30).

Rewriting all 33 in one pass is out of scope here and would touch files this
change has no way to validate individually. Instead this is a ratchet: the
existing set is a recorded BASELINE (debt, not blessed), and the check fails
CI only when a *new* file matching the pattern is added without either
importing a chokepoint or being added to BASELINE with a reason. That is the
concrete enforcement the doc-only reminder (that failed same-day, once
already) was missing.

Usage:
    python scripts/check_bypass_loaders.py            # scan, exit 1 on new bypass
    python scripts/check_bypass_loaders.py --list      # print current bypass set
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("scripts", "strategies")

_LOADER_DEF = re.compile(r"^def (load_(data|csv|ohlcv)|_load_(data|csv|ohlcv))\s*\(", re.MULTILINE)
_CHOKEPOINT_IMPORT = re.compile(
    r"BacktestEngine|load_provenance_checked|require_cost_calibrated|" r"from provenance import|^import provenance",
    re.MULTILINE,
)

# Recorded 2026-07-30 via this scanner. Not reviewed file-by-file for whether
# each one actually makes trial-verdict decisions (some are diagnostics/EDA
# that may not need the gate) -- that classification is still open. Do not
# add new entries here to silence the check; fix the import or get a
# reasoned exemption instead.
BASELINE: frozenset[str] = frozenset(
    {
        "scripts/audit_lookahead_v3.py",
        "scripts/build_features_v3_multi_asset.py",
        "scripts/cross_validate.py",
        "scripts/diagnose_features.py",
        "scripts/diagnose_regime_accuracy.py",
        # factor_control_check.py: PERMANENT exemption, reviewed 2026-07-30.
        # Its _load_csv is a generic float-column CSV reader (no OHLCV, no
        # price, no cost) matching the scanner's naming regex by accident.
        # run_factor_control() computes R² between two caller-supplied return
        # series -- there is no cost or data-loading logic to gate here at
        # all. Importing a chokepoint symbol just to satisfy the regex would
        # be a dishonest no-op, so this stays in BASELINE by design rather
        # than being "fixed." See reports/bypass_loader_classification_20260730.md.
        "scripts/factor_control_check.py",
        "scripts/regime_filter.py",
        "scripts/research_approaches.py",
        "scripts/research_dashboard.py",
        "scripts/retrain_calibrated.py",
        "scripts/run_multi_instrument_wf.py",
        # run_walk_forward.py: PERMANENT exemption, reviewed/fixed 2026-07-30.
        # This orchestrator only loads OHLCV data itself (load_ohlcv_*) --
        # it never makes a cost decision directly. Its real risk was a
        # broken --cost-config pass-through to two subprocess scripts,
        # documented and fixed as Finding 2/3 in
        # reports/bypass_loader_classification_20260730.md: walk_forward.py
        # checked `symbol in config` against the JSON's top-level keys
        # (never true) and read nonexistent field names, so its calibrated-
        # cost branch never fired; backtest_cost.py didn't even accept
        # --cost-config and hard-errored on every call. Both now import
        # provenance.require_cost_calibrated directly and raise loudly for
        # uncalibrated symbols instead of silently falling back to the flat
        # CLI defaults. Verified live: EURUSD raises UncalibratedCostError
        # in both Phase 4 and Phase 5 subprocess calls; XAUUSD prints
        # "[Calibrated cost] XAUUSD: round_trip=0.000065" (real) and runs.
        "scripts/run_walk_forward.py",
        # A pre-existing, unrelated `t0` NameError in load_ohlcv_from_parquet
        # was also fixed (blocked Phase 1 for any real parquet data before
        # the cost-config fix could even be exercised). backtest_cost.py
        # also has its own separate real-slippage source (a fill simulator)
        # that is loaded and printed but never actually used in the cost
        # computation -- documented as Finding 3, deliberately NOT fixed
        # here since wiring it in needs point-value/contract-size tracing
        # this session did not do (advisor-flagged boundary).
        "scripts/select_tradeable_instruments.py",
        "scripts/split_direction_c_holdout.py",
        "scripts/stress_test.py",
        "scripts/train_live_model.py",
        "scripts/train_mega_model.py",
        "scripts/train_mega_model_v2.py",
        "scripts/tsm_backtest_real_costs.py",
        "scripts/tsm_paper_trade.py",
        "scripts/validate_dtsmom_strategy.py",
        # NOTE 2026-07-30: the 5 entries below that mention get_round_trip_cost_bps
        # originally used get_spread_bps (one-way spread), which understates
        # real round-trip cost 2x for XAUUSD and ~59x for USDJPY (commission
        # not included in the one-way field). Corrected same-day; see Finding 1
        # in reports/bypass_loader_classification_20260730.md. No verdict
        # flipped from the correction (re-verified live + 81/81 regression).
        # validate_ram_strategy.py, test_ram_strategy.py removed 2026-07-30:
        # both now import provenance.require_cost_calibrated and gate on it
        # (verified live: UncalibratedCostError on XAGUSD).
        # tsm_backtest.py/tsm_ema.py/tsm_portfolio.py/tsm_validate.py removed
        # 2026-07-30: share one ASSETS list, now gated via the new
        # provenance.require_cost_calibrated_tsm_asset alias-resolving
        # helper (verified live: UncalibratedCostError on EURUSD in all 4).
        # run_rydc_validation.py removed 2026-07-30: previously had NO cost
        # term anywhere (worse than a flat-assumed cost); now gated on
        # XAUUSD via require_cost_calibrated and subtracts its real
        # measured round-trip spread (get_round_trip_cost_bps) per trade at exit.
        # Verdict stayed FAIL after the fix (verified live re-run).
        # comprehensive_edge_search.py removed 2026-07-30: flat cost_bps=10
        # replaced with real get_round_trip_cost_bps per symbol; XAUUSD-only prongs
        # use a real XAU_COST_BPS constant, the 10-instrument new_search
        # scan now skips any symbol not in provenance.cost_calibrated_symbols() instead
        # of guessing its cost (verified live: XAGUSD/XPTUSD/XPDUSD/EURUSD/
        # GBPUSD/AUDUSD/BTCUSD/ETHUSD skipped, XAUUSD/USDJPY ran for real).
        # See reports/bypass_loader_classification_20260730.md.
        # research_backed_pipeline.py removed 2026-07-30: flat cost_bps=10
        # default (simulate/expanding_wf_validate/holdout_validate/
        # build_adaptive_ensemble) replaced with real measured XAUUSD spread
        # (get_round_trip_cost_bps) -- every strategy in this file trades XAUUSD only.
        # Verified live full run: momentum_12m PASS_TO_NEXT_PHASE 7/7 gates,
        # other strategies ARCHIVE_NO_EDGE, no crash from the cost gate.
        # run_new_strategies_wf.py removed 2026-07-30: --cost-bps default
        # changed from a flat 10.0 to None -- when omitted, each strategy
        # now resolves its own real measured cost (get_round_trip_cost_bps) if all
        # its symbols are calibrated, else is skipped with a message
        # (pgm_pairs: XPTUSD/XPDUSD, momentum_factor_rotation: mixed with
        # XAGUSD/XPDUSD/XPTUSD -- neither calibrated). An explicit
        # --cost-bps flag from the user still overrides for all strategies
        # -- that's an informed choice, not a silent fabrication. Verified
        # live: pgm_pairs and momentum_factor_rotation SKIPPED by default,
        # fomc_drift (XAUUSD-only) ran to a real verdict with real cost.
        # run_complete_analysis.py removed 2026-07-30: hardcoded SYMBOLS
        # spread/slippage snapshot replaced with a live gate + real
        # get_round_trip_cost_bps read for XAUUSD; EURUSD/GBPUSD (not in
        # cost_calibrated_symbols()) skipped rather than run on the stale
        # copy. No slippage figure is measured anywhere in
        # cost_calibration.json, so slippage_p90 is set to 0 instead of
        # keeping a guess. Verified live: XAUUSD M15/H1 ran with real cost
        # ($3427/$2346 total cost on ~15k trades), EURUSD/GBPUSD SKIPPED.
        # run_multi_symbol_wf.py removed 2026-07-30: same hardcoded-COSTS
        # pattern as run_complete_analysis.py, same fix -- live gate +
        # get_round_trip_cost_bps, EURUSD/GBPUSD skipped. Verified live:
        # both SKIPPED with the cost-calibration message.
        # full_pipeline.py removed 2026-07-30: flat cost_bps=10 default
        # (simulate()/run_wf_validation()/validate_holdout()/build_ensemble()
        # all took it as a bare default) replaced with the real measured
        # XAUUSD spread (get_round_trip_cost_bps). The WF step's donchian_20_eurusd
        # entry (real per-symbol data via load_csv) is now skipped rather
        # than cost-guessed since EURUSD isn't in cost_calibrated_symbols();
        # the holdout step always reads XAUUSD-only holdout.csv regardless
        # of nominal symbol, so it uses the real XAUUSD spread for all 5
        # entries. Verified live: WF skip message printed for EURUSD,
        # config print showed cost_bps=0.65 (real round-trip) not 10 (guess); the
        # holdout step's FileNotFoundError on sacred_holdout/holdout.csv is
        # a pre-existing missing-data gap (same class as
        # comprehensive_edge_search.py's --prong holdout), not caused by
        # this change.
    }
)


def find_bypassing_files() -> list[str]:
    hits = []
    for d in SCAN_DIRS:
        for path in sorted((PROJECT_ROOT / d).glob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _LOADER_DEF.search(text) and not _CHOKEPOINT_IMPORT.search(text):
                hits.append(f"{d}/{path.name}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Chokepoint-bypass loader scanner")
    parser.add_argument("--list", action="store_true", help="print current bypass set and exit 0")
    args = parser.parse_args()

    found = find_bypassing_files()

    if args.list:
        for f in found:
            tag = "baseline" if f in BASELINE else "NEW"
            print(f"[{tag}] {f}")
        return 0

    new = [f for f in found if f not in BASELINE]
    if new:
        print("NEW chokepoint-bypassing loader(s) detected -- not in BASELINE:")
        for f in new:
            print(f"  {f}")
        print(
            "\nEach of these defines its own load_data/load_csv/load_ohlcv and never "
            "imports BacktestEngine or provenance.py. This is exactly the pattern that "
            "let trial #1030 fabricate cost data undetected. Either import a chokepoint "
            "(load_provenance_checked for data loading, require_cost_calibrated before "
            "any cost assumption), or add the file to BASELINE in this script with a "
            "reason (e.g. it's a diagnostic that never informs a trial verdict)."
        )
        return 1

    print(f"OK -- no new bypassing loaders ({len(found)} known baseline entries unchanged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
