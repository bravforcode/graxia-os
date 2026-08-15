#!/usr/bin/env python3
"""TF probe — H1/H4 adaptation for M15 scalper strategies (EA-BENCH 1034/1035 follow-up).

Probe semantics (approved 2026-08-05 design review):
  * AS-IS parameter transfer from M15 to H1/H4 — NOT an optimal-TF finding.
    Strategies are M15-tuned; tuning happens AFTER mapping selection.
  * Gross metrics (gross PF / gross Sharpe) are cost-independent -> valid for
    ALL symbols in this probe.
  * Cost-based classification (break_even_mult, cost_driven verdict) is ONLY
    emitted for symbols with stable measured costs (XAUUSD, USDJPY).
# 2026-08-06 (9003): EURUSD moved to stable — unit-corrected RT cost 0.78bps
# (FROM_TICKS, 56,115 ticks, 4.42d). Old 14.17bps was an 8-29x unit overstatement.
  * EURUSD/GBPUSD break_even fields are null with blocked_on reasons:
      - direction_g_step1_completion (EURUSD round-trip moved 7.18->14.17 bps
        during this session; re-measurement in progress)
      - tradeable_universe.json contradiction (symbols in BOTH measuring and
        excluded arrays) unresolved
    NO cost-based numbers are written for those symbols to prevent stale
    numbers being cited later.

Selection rule (per symbol): gross_sharpe_daily > 0 AND n_trades >= 30 AND
break_even_mult >= 1.2 (margin absorbs cost-revision swings — evidenced by the
EURUSD 7.18->14.17 bps swing). Tiebreak: highest gross_sharpe_daily.
Break_even gate only applies where break_even_mult is emitted (XAUUSD/USDJPY).

Output: reports/edge_search_tf_probe.json (PERMANENT evidence artifact —
n_combos_searched must be cited in any follow-up pre-registration to account
for selection bias in DSR N).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for _p in (str(GRAXIA_ROOT), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from graxia.packages.quant_os.provenance import require_cost_calibrated  # noqa: E402
from graxia.packages.quant_os.scripts.edge_search_m15_scalper import (  # noqa: E402
    COMMISSION_PER_LOT,
    INITIAL_CAPITAL,
    MAX_BARS_OPEN,
    RISK_PER_TRADE_BPS,
    compute_asset_metrics,
    gross_reconstruct,
    strategy_for,
)

CORE_ASSETS = ["XAUUSD", "USDJPY", "EURUSD", "GBPUSD"]
TFS = ["H1", "H4"]
BARS_PER_HOUR = {"M15": 4, "H1": 1, "H4": 0.25}

# Symbols with STABLE measured costs -> full classification emitted.
COST_STABLE_SYMBOLS = frozenset({"XAUUSD", "USDJPY", "EURUSD"})
# Symbols blocked from cost-based fields pending Direction G + universe fix.
COST_BLOCKED = {
    # EURUSD removed 2026-08-06 (9003 pre-registration): Direction G stopped
    # §4.4 + universe contradiction resolved C1.1 — break-even now computable.
    "GBPUSD": [
        "direction_g_step1_completion",
        "tradeable_universe.json contradiction (measuring AND excluded) unresolved",
    ],
}
MIN_TRADES_FOR_SELECTION = 30
BREAK_EVEN_MARGIN = 1.2  # survive >= 1.2x measured costs (margin vs cost-revision swings)
MIN_BARS = 500


def load_bars(symbol: str, tf: str) -> pd.DataFrame:
    """Load OHLCV bars for (symbol, tf) from data/{SYMBOL}_{TF}.csv."""
    path = ROOT / "data" / f"{symbol}_{tf}.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    if ts_col not in df.columns:
        raise ValueError(f"{symbol}: no time/date column in {path.name}")
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.sort_values(ts_col).reset_index(drop=True)
    if len(df) < MIN_BARS:
        raise ValueError(f"{symbol}: only {len(df)} bars (< {MIN_BARS})")
    return df


def run_asset_engine_tf(symbol: str, tf: str) -> dict:
    """Run one asset through the engine on the given TF (measured-cost path).

    max_bars_open (M15-scaled session exit) is scaled by bars-per-hour:
    H1 -> base // 4, H4 -> base // 16 (min 1).
    """
    df = load_bars(symbol, tf)
    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df),
    }
    timestamps = df["time"].tolist()

    scale = BARS_PER_HOUR[tf] / BARS_PER_HOUR["M15"]
    max_bars_open = max(int(MAX_BARS_OPEN.get(symbol, 32) * scale), 1)

    # 9003 (2026-08-06): measured-cost override — spread ~0.087bps ≈ 1 tick
    # (tick_size 1e-05), slippage 0 (no fill sim; honest). Engine L1182 takes
    # both overrides directly → no profile lookup → no UnmeasuredCostError.
    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        slippage_pips=0,
        spread_pips=1,
        commission_per_lot=COMMISSION_PER_LOT.get(symbol, 0.0),
        risk_per_trade_bps=RISK_PER_TRADE_BPS,
        max_positions=1,
        strict_mtf=False,
        enable_swap=False,
        max_bars_open=max_bars_open,
    )
    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(strategy_for(symbol))
    engine.load_data(ohlcv, timestamps)
    # Same optimizations as edge_search_m15_scalper.run_asset_engine:
    # classic equity path + skip per-bar precomputed indicator slicing.
    engine._pnl_tracker = None
    engine._precomputed_indicators = {}

    result = engine.run()
    return {
        "symbol": symbol,
        "trades": result.get("trades", []),
        "equity_curve": result.get("equity_curve", []),
        "first_bar": timestamps[0].isoformat(),
        "last_bar": timestamps[-1].isoformat(),
    }


def measured_round_trip_bps(symbol: str) -> float:
    calib = json.loads((ROOT / "config" / "cost_calibration.json").read_text(encoding="utf-8"))
    entry = calib.get("assets", {}).get(symbol, {})
    spread = float(entry.get("spread_bps_measured", 0.0))
    return float(entry.get("round_trip_bps_measured", spread * 2.0))


def probe_one(symbol: str, tf: str) -> dict:
    """Probe (symbol, tf): net + gross metrics; cost fields per stability."""
    ar = run_asset_engine_tf(symbol, tf)
    net = compute_asset_metrics(ar)
    cost_status = require_cost_calibrated(symbol, mode="paper")  # raises if unknown

    out = {
        "symbol": symbol,
        "tf": tf,
        "n_trades": net["n_trades"],
        "n_days": net["n_days"],
        "net_sharpe_daily": net["sharpe_daily"],
        "net_pf": net["profit_factor"],
        "net_win_pct": net["win_pct"],
        "cost_status": cost_status,
        "note": "AS-IS M15 parameter transfer — NOT optimal-TF finding (tuning deferred)",
    }

    if symbol in COST_STABLE_SYMBOLS:
        bps = measured_round_trip_bps(symbol)
        g = gross_reconstruct(ar, bps)
        out.update(
            {
                "gross_sharpe_daily": g["gross_sharpe_daily"],
                "gross_pf": g["gross_pf"],
                "gross_win_pct": g["gross_win_pct"],
                "break_even_mult": g["break_even_mult"],
                "break_even_round_trip_bps": g["break_even_round_trip_bps"],
                "measured_round_trip_bps": g["measured_round_trip_bps"],
                "classification": g["classification"],
            }
        )
    else:
        # Blocked symbols: gross-only (cost-independent); cost fields stay null.
        g = gross_reconstruct(ar, 0.0)
        classification = "structural" if g["gross_pf"] < 1.0 else "pending_cost"
        out.update(
            {
                "gross_sharpe_daily": g["gross_sharpe_daily"],
                "gross_pf": g["gross_pf"],
                "gross_win_pct": g["gross_win_pct"],
                "break_even_mult": None,
                "break_even_round_trip_bps": None,
                "measured_round_trip_bps": None,
                "classification": classification,
                "blocked_on": COST_BLOCKED.get(symbol, ["unknown"]),
            }
        )
    if out["n_trades"] < MIN_TRADES_FOR_SELECTION:
        # Sharpe is not statistically comparable below the project's minimum
        # trade count (MIN_TRADES_PER_ASSET = 30) — null it out so the
        # permanent artifact cannot be misquoted (see XAUUSD H4 case).
        out["net_sharpe_daily"] = None
        out["gross_sharpe_daily"] = None
        out["note"] = (
            f"insufficient trades ({out['n_trades']} < {MIN_TRADES_FOR_SELECTION}) "
            "for Sharpe comparability; values nulled"
        )
    return out


def select_mapping(runs: list[dict]) -> dict:
    """Apply the survival rule per symbol."""
    by_sym: dict[str, list[dict]] = {}
    for r in runs:
        by_sym.setdefault(r["symbol"], []).append(r)
    mapping = {}
    blocked = {}
    for sym, rr in by_sym.items():
        candidates = []
        for r in rr:
            if r["n_trades"] < MIN_TRADES_FOR_SELECTION:
                continue
            if r["gross_sharpe_daily"] <= 0:
                continue
            be = r.get("break_even_mult")
            if be is not None and be < BREAK_EVEN_MARGIN:
                continue
            if be is None and r["classification"] == "pending_cost":
                gross_srs = [x["gross_sharpe_daily"] for x in rr if x["gross_sharpe_daily"] is not None]
                blocked[sym] = {
                    "reason": "gross edge present but break_even pending",
                    "blocked_on": r.get("blocked_on", []),
                    "best_gross_sharpe": max(gross_srs) if gross_srs else None,
                }
                continue
            candidates.append(r)
        if candidates:
            best = max(candidates, key=lambda x: x["gross_sharpe_daily"])
            mapping[sym] = {
                "tf": best["tf"],
                "gross_sharpe_daily": best["gross_sharpe_daily"],
                "gross_pf": best["gross_pf"],
                "break_even_mult": best.get("break_even_mult"),
                "n_trades": best["n_trades"],
                "classification": best["classification"],
            }
        elif sym not in blocked and sym in COST_BLOCKED:
            # Blocked symbol with no gross edge -> structural either way
            mapping[sym] = {
                "tf": None,
                "reason": "no TF passed gross_sharpe>0 AND n_trades>=30 (structural at H1/H4)",
                "classification": "structural",
            }
        elif sym not in blocked:
            mapping[sym] = {"tf": None, "reason": "no TF passed the survival rule"}
    return {
        "rule": "gross_sharpe>0 AND n_trades>=30 AND break_even_mult>=1.2 (where emitted); tiebreak gross_sharpe",
        "mapping": mapping,
        "blocked": blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TF probe H1/H4 — as-is M15 transfer")
    parser.add_argument("--symbols", default=",".join(CORE_ASSETS))
    parser.add_argument("--tfs", default=",".join(TFS))
    parser.add_argument("--out", default="reports/edge_search_tf_probe.json")
    args = parser.parse_args()

    symbols = args.symbols.split(",")
    tfs = args.tfs.split(",")
    print("=" * 64)
    print("TF PROBE (H1/H4) — as-is M15 parameter transfer")
    print("NOT an optimal-TF finding; tuning deferred until mapping selected")
    print("=" * 64)

    runs = []
    for sym in symbols:
        for tf in tfs:
            try:
                r = probe_one(sym, tf)
                runs.append(r)
                print(
                    f"  {sym} {tf}: trades={r['n_trades']} net_sharpe={r['net_sharpe_daily']} "
                    f"gross_pf={r['gross_pf']} gross_sharpe={r['gross_sharpe_daily']} "
                    f"be_mult={r['break_even_mult']} class={r['classification']}"
                )
            except Exception as e:  # noqa: BLE001 — probe must not die on one combo
                print(f"  {sym} {tf}: FAILED — {e}")
                runs.append({"symbol": sym, "tf": tf, "error": str(e)})

    selection = select_mapping([r for r in runs if "error" not in r])

    artifact = {
        "title": "TF probe H1/H4 — M15 scalper strategy as-is transfer",
        "method": "as-is M15 parameters on H1/H4 bars; gross post-hoc reconstruction (same trade set)",
        "caveat": "AS-IS transfer only — NOT optimal-TF finding; M15-tuned params may underperform untuned at other TFs",
        "generated": datetime.now(UTC).isoformat(),
        "cost_policy": {
            "stable_measured": sorted(COST_STABLE_SYMBOLS),
            "blocked": COST_BLOCKED,
            "note": "no cost-based numbers emitted for blocked symbols (stale-by-construction guard)",
        },
        "selection_rule": selection["rule"],
        "runs": runs,
        "selection": selection,
        "n_combos_searched": len(symbols) * len(tfs),
        "multiple_testing_note": "N combos searched must be cited in any follow-up pre-registration DSR methodology",
    }

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\nProbe artifact written: {out}")
    print(f"Combos searched: {artifact['n_combos_searched']}")
    print("Mapping:", json.dumps(selection["mapping"], indent=1))
    if selection["blocked"]:
        print("Blocked (pending):", json.dumps(selection["blocked"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
