#!/usr/bin/env python3
"""
Strategy re-use guard — MEGA_PLAN v2 finding F21.

Before registering any strategies/*.py into the alpha engine, check whether
its mechanism was already tested and REJECTED/INCONCLUSIVE in the reconciled
trial ledger (reports/trial_count_reconciliation_20260720.json). Filename
alone is not reliable evidence either way: two strategies can share a
mechanism under different filenames (hybrid_mom_mr.py IS HybridMomMR_20/60
from the pooled edge search), and two files can look similar by name while
testing genuinely different mechanisms (mrb.py = rule-based Bollinger/RSI/
Stochastic; mlmr.py = XGBoost-confirmed mean reversion -- never tested).

This script encodes that mechanism mapping explicitly so the mapping is
reviewable, instead of guessing from filenames at registration time.

Usage:
    python scripts/check_strategy_against_ledger.py strategies/hybrid_mom_mr.py
    python scripts/check_strategy_against_ledger.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECONCILIATION_PATH = PROJECT_ROOT / "reports" / "trial_count_reconciliation_20260720.json"

# Mechanism mapping: strategies/*.py -> ledger record(s) it corresponds to.
# Built by reading each file's actual signal logic, not by filename similarity.
# status:
#   BLOCKED - same mechanism + same test population already REJECTED; do not
#             re-register without a documented reason the prior test was wrong.
#   CAUTION - shares a mechanism family with a REJECTED trial but has material
#             changes (added filters/exits); registering requires a NEW trial
#             number, a pre-registered hypothesis, and its own label-shuffle
#             test -- it is not automatically disproven, but it is not "unused
#             free money" either.
#   CLEAR   - no matching ledger record found; genuinely untested. Still must
#             go through the normal trial-ledger + multiple-testing pipeline,
#             just isn't pre-disproven.
#   UNGATED_POSITIVE - a positive/GO result already exists for this mechanism
#             (usually in a standalone reports/*.json file) but was never
#             entered into any trial ledger and never multiple-testing
#             corrected. Treat as MORE dangerous than CLEAR, not less: the
#             temptation is to register it as-is because it already "passed."
#             Do not register until it has a ledger entry, a documented N, and
#             has cleared validation/instrument_selection.py's BH correction
#             -- and until any data/unit-scaling artifacts are ruled out.
#   INFRA   - not an independently testable strategy (harness, wrapper,
#             filter, sizing overlay, dev script). No verdict applies.
STRATEGY_MECHANISM_MAP: dict[str, dict] = {
    "strategies/hybrid_mom_mr.py": {
        "class": "HybridMomMR",
        "status": "BLOCKED",
        "ledger_refs": ["HybridMomMR_20 (dk_t=-0.41)", "HybridMomMR_60 (dk_t=-0.42)"],
        "reason": (
            "Same mechanism (sign of N-bar mean return, XAUUSD) at both lookback "
            "params this file exposes (lookback=60 default, 20 also tested). "
            "Both REJECTED in EDGE_SEARCH_FINAL_20260718.md pooled DK-test."
        ),
    },
    "strategies/mlmr.py": {
        "class": "MLMeanReversion",
        "status": "CLEAR",
        "ledger_refs": [],
        "reason": (
            "Do not confuse with strategies/mrb.py (MeanReversionBollinger, rule-based "
            "ADX+BB+Stoch+RSI, no ML) -- that is the file behind the pooled ledger's "
            "'MRB_default' UNTESTABLE entry ('no signals ... ML Mean Reversion' note refers "
            "to the concept, not this file). mlmr.py's XGBoost-confirmed BB touch was never "
            "run through edge_search_all.py or any ledger trial. Genuinely untested."
        ),
    },
    "strategies/liquidity_sweep.py": {
        "class": "LiquiditySweep",
        "status": "BLOCKED",
        "ledger_refs": ["LiquiditySweep (dk_t=-0.52, trades=2763)"],
        "reason": "Exact mechanism REJECTED in pooled DK-test.",
    },
    "strategies/liquidity_sweep_v2.py": {
        "class": "LiquiditySweepV2",
        "status": "CAUTION",
        "ledger_refs": ["LiquiditySweep (dk_t=-0.52, trades=2763)"],
        "reason": (
            "Same core sweep-detection mechanism as the REJECTED v1, but adds RSI/volume "
            "confirmation filters, ATR trailing stop, and regime-aware sizing -- materially "
            "different rule set. Not pre-disproven, but must be registered as its own "
            "pre-registered hypothesis with its own trial number and label-shuffle test, "
            "not silently added to the alpha engine as if it were fresh."
        ),
    },
    "strategies/rsi_mean_reversion.py": {
        "class": "RSIMeanReversion",
        "status": "BLOCKED",
        "ledger_refs": ["RSI_20_80 (dk_t=-0.22)", "RSI_30_70 (dk_t=-0.36)", "RSI_25_75 (dk_t=-0.82)"],
        "reason": "All threshold variants of this exact mechanism REJECTED in pooled DK-test.",
    },
    "strategies/momentum_12m.py": {
        "class": "Momentum12M",
        "status": "BLOCKED",
        "ledger_refs": ["Momentum12M_252 (dk_t=-0.39)", "Momentum12M_126 (dk_t=-0.52)"],
        "reason": "Both lookback variants REJECTED in pooled DK-test.",
    },
    "strategies/donchian.py": {
        "class": "Donchian",
        "status": "BLOCKED",
        "ledger_refs": ["Donchian_10 (dk_t=-0.61)", "Donchian_20 (dk_t=-0.75)", "Donchian_55 (dk_t=-0.59)"],
        "reason": "All channel-length variants REJECTED in pooled DK-test.",
    },
    "strategies/donchian_adx.py": {
        "class": "DonchianADX",
        "status": "BLOCKED",
        "ledger_refs": ["DonchianADX_10_25 (dk_t=-0.53)"],
        "reason": "REJECTED in pooled DK-test.",
    },
    "strategies/bollinger_squeeze.py": {
        "class": "BollingerSqueeze",
        "status": "BLOCKED",
        "ledger_refs": ["BollingerSqueeze_p20 (dk_t=-0.60)"],
        "reason": "REJECTED in pooled DK-test.",
    },
    "strategies/volume_breakout.py": {
        "class": "VolumeBreakout",
        "status": "BLOCKED",
        "ledger_refs": ["VolumeBreakout_1.5 (dk_t=-0.77)", "VolumeBreakout_2.0 (dk_t=-0.49)"],
        "reason": "Both threshold variants REJECTED in pooled DK-test.",
    },
    "strategies/rydc.py": {
        "class": "RYDC",
        "status": "BLOCKED",
        "ledger_refs": ["Direction A trial 1001 (rydc_arm_a, REJECTED)"],
        "reason": "REJECTED in trial_ledger.json Direction A.",
    },
    "strategies/cross_asset_momentum.py": {
        "class": "CrossAssetMomentum",
        "status": "BLOCKED",
        "ledger_refs": ["Direction A trial 1003 (cross_asset_momentum, p=0.598)"],
        "reason": "REJECTED, part of the 4-consecutive-failure stopping-rule trigger chain.",
    },
    "strategies/session_pattern.py": {
        "class": "SessionPattern",
        "status": "BLOCKED",
        "ledger_refs": ["Direction A trial 1004 (session_pattern, p=0.934)"],
        "reason": "REJECTED, part of the 4-consecutive-failure stopping-rule trigger chain.",
    },
    "strategies/macro_regime_mr.py": {
        "class": "MacroRegimeMR",
        "status": "BLOCKED",
        "ledger_refs": ["Direction A trial 1005 (macro_regime_mr, p=0.244)"],
        "reason": "REJECTED, part of the 4-consecutive-failure stopping-rule trigger chain.",
    },
    "strategies/gold_silver_spread.py": {
        "class": "GoldSilverSpread",
        "status": "BLOCKED",
        "ledger_refs": ["Direction A trial 1006 (gold_silver_spread, p=0.505)"],
        "reason": "REJECTED, part of the 4-consecutive-failure stopping-rule trigger chain.",
    },
    # --- Batch 2, added after cross-referencing trial_ledger_b.json,
    # trial_ledger_c.json (Direction C, crypto vol strategies), and
    # path_b_wrappers.py's registry. Several files' own docstrings cite
    # stale/wrong trial numbers (verified against the actual ledgers, not
    # trusted at face value) -- noted per-entry where that happened.
    "strategies/btc_eth_vol_spread.py": {
        "class": "compute_bevs_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_c.json #3003 BEVS-BTC-ETH-VOL-SPREAD (REJECTED, p=0.1877)"],
        "reason": (
            "Config matches trial 3003 exactly (Sharpe 1.28 but only 68 trades, "
            "REJECTED as underpowered). File's own docstring cites '#2003' -- stale, "
            "actual ledger entry is 3003."
        ),
    },
    "strategies/btc_vol_clustering.py": {
        "class": "compute_bvc_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger.json #1007 BVC-BTC-VOL-CLUSTERING (REJECTED, p=0.2479)"],
        "reason": "Verified against trial_ledger.json: 72.4% win rate but only 29 trades < 100 target.",
    },
    "strategies/btc_vol_divergence.py": {
        "class": "compute_btcvd_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_c.json #3001 btc_vol_divergence (REJECTED, p=0.5533)"],
        "reason": (
            "Config matches trial 3001 exactly (6 trades, negative Sharpe). File's own "
            "docstring cites '#2001' -- stale. Ref corrected from stale '3004' to '3001' "
            "2026-07-31 after trial_ledger_c.json's own internal numbering was fixed "
            "(see TRIAL_ID_RANGES.md)."
        ),
    },
    "strategies/carry.py": {
        "class": "compute_carry_signal",
        "status": "CAUTION",
        "ledger_refs": [
            "trial_ledger_b.json #2001 PATHB-CARRY-XAUUSD (REJECTED-but-INVALIDATED: tested "
            "with DGS10-DGS2 yield curve, not real FX carry)",
            "trial_ledger_b.json #2008 PATHB-CARRY-FX-XAUUSD (UNTESTED, blocked on missing " "EUR/JPY rate data)",
        ],
        "reason": (
            "This is the generic function path_b_wrappers.CarryStrategy calls. The only "
            "prior run used the wrong input data (yield curve slope, not a real carry "
            "differential) so its REJECT is not a clean disproof of the real mechanism; the "
            "correctly-specified version has never been run at all."
        ),
    },
    "strategies/cot_positioning.py": {
        "class": "compute_cot_positioning_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_b.json #2007 PATHB-COT-XAUUSD (REJECTED, dk_t=-0.338, 40 trades)"],
        "reason": (
            "Config matches path_b_wrappers.COTPositioningStrategy defaults exactly (source "
            "of COT_default in the pooled test). File's own docstring cites '#1009' -- stale, "
            "1009-1021 is actually the unrelated gold_ict_batch."
        ),
    },
    "strategies/cross_asset_vol_rank.py": {
        "class": "compute_cvr_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger.json #1008 CVR-CROSS-ASSET-VOL-RANK (REJECTED, p=0.6101)"],
        "reason": "Verified against trial_ledger.json: negative Sharpe, 1/6 gates passed.",
    },
    "strategies/donchian_p1.py": {
        "class": "DonchianBandStop",
        "status": "BLOCKED",
        "ledger_refs": [
            "trial_ledger_b.json #2009 DONCHIAN20-8ASSET (REJECTED, dk_t=3.68)",
            "trial_ledger_b.json #2010 DONCHIAN20-VOLFILTER-8ASSET (REJECTED, dk_t collapsed "
            "7.93->3.32 post symbol-fix, then ->-0.14/-1.01 on jackknife excluding XAGUSD)",
        ],
        "reason": (
            "RESOLVED 2026-07-28 (was UNGATED_POSITIVE): the original dk_t=+7.93/+6.10 GO result "
            "(2026-07-19) was produced before that same day's commit 59a15bd0 fixed a "
            "symbol-threading bug (non-XAUUSD contract specs defaulted to gold-shaped values). "
            "Post-fix re-run collapsed dk_t to 3.32-3.68 but did not zero it out; jackknife "
            "(leave-one-asset-out) then showed the entire surviving signal is carried by XAGUSD "
            "alone -- confirmed missing from InlineContractSpec.for_symbol()'s symbol map "
            "(backtest/engine.py), same root-cause bug class, still unfixed. Excluding XAGUSD "
            "flips pooled dk_t from +3.32 to -0.14. REJECTED. Full chain: "
            "reports/f27_pip_scaling_verification_20260728.md."
        ),
    },
    "strategies/dxy_divergence.py": {
        "class": "DXYDivergence",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_b.json #2004 PATHB-DXY-DIV-XAUUSD (REJECTED, dk_t=-1.4327)"],
        "reason": (
            "Confirmed via edge_search_all.py registry as 'DXYDiv_default'. Note: despite the "
            "name, the code has no actual DXY input -- self-referential 10-bar return sign only. "
            "That is still the tested (and REJECTED) mechanism."
        ),
    },
    "strategies/event_filter.py": {
        "class": "EventFilter",
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "FOMC/CPI date-exclusion utility consumed by fomc_drift.py -- no signal of its own, not independently registrable.",
    },
    "strategies/factor_signals.py": {
        "class": "compute_factor_signals",
        "status": "CAUTION",
        "ledger_refs": [
            "tsmom.py #2005 (REJECTED)",
            "carry.py #2001/#2008 (invalidated/untested)",
            "pairs_mr.py (untested)",
        ],
        "reason": (
            "Weighted combiner (TSMOM 0.5 + Carry 0.3 + PairsMR 0.2) never itself DK-tested -- "
            "a new ensemble built partly from an already-REJECTED component at 50% weight."
        ),
    },
    "strategies/fomc_drift.py": {
        "class": "compute_fomc_drift_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_b.json #2006 PATHB-FOMC-XAUUSD (REJECTED, dk_t=-0.984, 305 trades)"],
        "reason": (
            "Config matches path_b_wrappers.FOMCDriftStrategy defaults exactly (source of "
            "FOMC_default). File's own docstring cites '#1010' -- stale."
        ),
    },
    "strategies/mtm.py": {
        "class": "MultiTimeframeMomentum",
        "status": "CLEAR",
        "ledger_refs": ["EDGE_SEARCH_FINAL_20260718.md: 'MTM_default ... NO SIGNALS (needs MTF indicators)'"],
        "reason": "Harness never computed the H1/H4 EMA200 inputs so 0 signals were generated -- no DK-test verdict exists, genuinely untested.",
    },
    "strategies/mrb.py": {
        "class": "MeanReversionBollinger",
        "status": "CLEAR",
        "ledger_refs": ["EDGE_SEARCH_FINAL_20260718.md: 'MRB_default ... NO SIGNALS (needs indicators)'"],
        "reason": "Confirmed rule-based BB/ADX/Stochastic/RSI. Harness never computed those indicators so 0 signals -- no verdict recorded. Not to be confused with mlmr.py (different file, different mechanism).",
    },
    "strategies/orderflow_imbalance.py": {
        "class": "compute_orderflow_imbalance_signals",
        "status": "CLEAR",
        "ledger_refs": [],
        "reason": (
            "No match in trial_ledger.json/_b/_c. File's own docstring '#1012' doesn't match "
            "anything (1009-1021 is the unrelated gold_ict_batch). CLV-cumsum mechanism "
            "genuinely untested."
        ),
    },
    "strategies/pairs_mr.py": {
        "class": "compute_pairs_mr_signal",
        "status": "CLEAR",
        "ledger_refs": [],
        "reason": "No match in any of the 3 ledgers. Generic two-asset z-score, consumed by factor_signals.py/pgm_pairs.py but never itself a registered trial.",
    },
    "strategies/pgm_pairs.py": {
        "class": "compute_pgm_pairs_signals",
        "status": "CLEAR",
        "ledger_refs": [],
        "reason": "File's own docstring '#1009' doesn't match (that's the gold_ict_batch, not PGM). No platinum/palladium entry in any ledger. Genuinely untested.",
    },
    "strategies/funding_rate_arb.py": {
        "class": "FundingRateArbitrage",
        "status": "CLEAR",
        "ledger_refs": [
            "EDGE_SEARCH_FINAL_20260718.md: listed under 'Strategies NOT Testable ... needs crypto funding feed'"
        ],
        "reason": "Requires an external perp-funding-rate feed absent from the data pipeline entirely; no entry anywhere.",
    },
    "strategies/donchian_rsi.py": {
        "class": "DonchianRSI",
        "status": "CAUTION",
        "ledger_refs": [
            "EDGE_SEARCH_FINAL_20260718.md: Donchian_10/20/55 (dk_t -0.61/-0.75/-0.59, REJECT)",
            "EDGE_SEARCH_FINAL_20260718.md: RSI_20_80/25_75/30_70 (dk_t -0.22/-0.82/-0.36, REJECT)",
        ],
        "reason": "Combines two independently-REJECTED families (Donchian breakout + RSI filter) plus a new vol-percentile filter -- this exact hybrid was never itself tested.",
    },
    "strategies/tsm_dxy_divergence.py": {
        "class": "TSMDXYDivergence",
        "status": "BLOCKED",
        "ledger_refs": [
            "trial_ledger_b.json #2011 TSM-DXY-DIVERGENCE-8ASSET (REJECTED, dk_t collapsed "
            "4.95->2.90 post symbol-fix)",
            "trial_ledger_b.json #2004/#2005 (DXYDiv/TSMOM REJECTED) are a DIFFERENT, simpler "
            "mechanism -- not the same code",
        ],
        "reason": (
            "RESOLVED 2026-07-28 (was UNGATED_POSITIVE): same governance gap and same root "
            "cause as donchian_p1.py -- original +4.95 GO predates the same-day symbol-threading "
            "fix (commit 59a15bd0). Post-fix dk_t=2.90. This strategy's own per-asset table "
            "shows the identical XAGUSD outlier signature (nw_t=3.13, PF=9.65, far above every "
            "other asset) that donchian_p1's direct jackknife proved is a contract-spec artifact "
            "(XAGUSD missing from InlineContractSpec.for_symbol()). Not independently "
            "re-jackknifed for this exact strategy, but same universe/engine/defect -- inferred "
            "REJECTED, not directly re-tested. Full chain: "
            "reports/f27_pip_scaling_verification_20260728.md."
        ),
    },
    "strategies/three_stage_pipeline.py": {
        "class": "ThreeStagePipeline",
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "Orchestration layer (HAR vol forecast -> regime gate -> factor_signals), no signal of its own; composes untested/partly-rejected components but isn't itself registrable.",
    },
    "strategies/tsmom.py": {
        "class": "compute_tsmom_signal",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_b.json #2005 PATHB-TSMOM-XAUUSD (REJECTED, dk_t=-1.267, -1.514 in 100k rerun)"],
        "reason": "Confirmed via edge_search_all.py + path_b_wrappers.TSMOMStrategy -- this function (lookbacks [21,63,252]) is literally wrapped to produce TSMOM_default.",
    },
    "strategies/vol_regime_sizing.py": {
        "class": "compute_vol_regime_sizing",
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "Explicitly a position-sizing overlay, not a directional signal -- no buy/sell logic, cannot be REJECTED/GO gated on its own.",
    },
    "strategies/vol_risk_premium.py": {
        "class": "compute_vol_risk_premium_signals",
        "status": "BLOCKED",
        "ledger_refs": ["trial_ledger_b.json #2002 PATHB-VRP-XAUUSD (REJECTED, dk_t=-1.101, 546 trades)"],
        "reason": (
            "Config matches path_b_wrappers.VolRiskPremiumStrategy's inline VRP calc exactly "
            "(source of VRP_default). File's own docstring cites '#1014' -- stale."
        ),
    },
    "strategies/path_b_wrappers.py": {
        "class": None,
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "Thin Strategy-ABC adapters over carry.py/tsmom.py/cross_asset_momentum.py/fomc_drift.py/cot_positioning.py + inline VRP calc. Its own docstring says 'no new logic, no parameter changes' -- not an independent hypothesis.",
    },
    "strategies/walk_forward.py": {
        "class": "WalkForwardValidator",
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "Generic fold-split/Sharpe/PBO/deflated-Sharpe validation harness for any Strategy object -- no generate_signal, no market view of its own.",
    },
    "strategies/grid_strategy.py": {
        "class": "GridStrategy",
        "status": "CLEAR",
        "ledger_refs": [],
        "reason": "Standalone equidistant-grid market-making mechanism, structurally unlike everything in all 3 ledgers/both reports. Genuinely new/untested (also note: grid strategies have their own well-known blow-up risk profile independent of statistical edge -- treat with normal risk scrutiny even though it's not pre-disproven).",
    },
    "strategies/grid_backtest.py": {
        "class": "run_grid_backtest",
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "Backtest harness specific to grid_strategy.py's GridConfig, with its own P&L/drawdown engine bypassing BacktestEngine entirely. No independent signal.",
    },
    "strategies/_grid_smoke.py": {
        "class": None,
        "status": "INFRA",
        "ledger_refs": [],
        "reason": "Dev smoke-test script printing grid_backtest results for 6 hardcoded configs. Not a strategy, no ledger relevance.",
    },
}


def check(path_arg: str) -> dict:
    key = path_arg.replace("\\", "/")
    if not key.startswith("strategies/"):
        key = f"strategies/{Path(key).name}"
    entry = STRATEGY_MECHANISM_MAP.get(key)
    if entry is None:
        return {
            "file": key,
            "status": "UNMAPPED",
            "reason": (
                "No mechanism mapping recorded for this file yet. Do NOT treat this as "
                "CLEAR -- it means nobody has checked it against the ledger. Read the "
                "file's actual signal logic and add an entry to STRATEGY_MECHANISM_MAP "
                "before registering it into the alpha engine."
            ),
        }
    return {"file": key, **entry}


def main() -> int:
    parser = argparse.ArgumentParser(description="F21 strategy re-use guard")
    parser.add_argument("paths", nargs="*", help="strategies/*.py paths to check")
    parser.add_argument("--all", action="store_true", help="check every mapped strategy")
    args = parser.parse_args()

    if not RECONCILIATION_PATH.exists():
        print(
            f"WARNING: {RECONCILIATION_PATH} not found -- run "
            "scripts/reconcile_trial_ledger.py first. Proceeding with the static "
            "mechanism map only.",
            file=sys.stderr,
        )

    targets = list(STRATEGY_MECHANISM_MAP.keys()) if args.all else args.paths
    if not targets:
        parser.print_help()
        return 1

    blocked = 0
    for t in targets:
        result = check(t)
        print(json.dumps(result, indent=2))
        if result["status"] in ("BLOCKED", "UNMAPPED", "UNGATED_POSITIVE"):
            blocked += 1

    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
