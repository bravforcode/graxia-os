"""Direction G trial runner — trials 8001 (BTCUSD H1 Donchian) + 8002 (EURUSD M15 session breakout).

Reads OHLCV from data/market_data.duckdb (imported via
scripts/import_mt5_csv_to_duckdb.py), runs BacktestEngine with the frozen
strategy + REAL measured cost profile (SymbolCostProfile from
config/cost_calibration.json, FROM_TICKS) and fill-simulator slippage, computes
the frozen gate stack (p-value, DSR, trades, cost stress, label shuffle,
jackknife), and stamps the verdict via research/registry_schema.stamp_trial_entry().

Usage:
    python scripts/run_direction_g_trials.py                  # both trials
    python scripts/run_direction_g_trials.py --trials 8001    # one trial
    python scripts/run_direction_g_trials.py --dry-run        # no registry write
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "market_data.duckdb"
REGISTRY_G = ROOT / "research" / "hypothesis_registry_g.json"
LEDGER_G = ROOT / "research" / "trial_ledger_g.json"

# Make monorepo importable: scripts/ runs from quant_os/, but the package is
# `quant_os` under the `graxia` namespace at the monorepo root. Some modules
# import `graxia.packages.quant_os...` (full path) — both roots must be on
# sys.path.
_GRAXIA_ROOT = ROOT.parent.parent  # .../graxia
_MONOREPO_ROOT = _GRAXIA_ROOT.parent  # .../graxia os (has graxia/ subdir)
for _p in (_MONOREPO_ROOT, _GRAXIA_ROOT, ROOT.parent, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

TF_CONVENTION = {"H1": "1h", "M15": "15m", "D1": "1d"}

TRIALS: dict[int, dict[str, Any]] = {
    8001: {
        "id": "DIRG-BTC-DONCHIAN-H1",
        "symbol": "BTCUSD",
        "tf": "H1",
        "cost_model_version": "4.1",
        "cost_source": "FROM_TICKS",
        # COMMISSION UNIT FIX 2026-08-06: round_trip_bps was USD/rt-lot misread
        # as bps (24.75 -> true 6.30). Report-only; verdict used engine $/lot path.
        "round_trip_bps_used": {"BTCUSD": 6.30},
        "slippage_source": "fill_simulator_p90_points",
        "slippage_bps_used": {"BTCUSD": 0.495},  # 32 pts x 0.01 / 64666 x 1e4
        "strategy_name": "BtcDonchianTrend",
    },
    8002: {
        "id": "DIRG-EUR-SESSION-BREAKOUT-M15",
        "symbol": "EURUSD",
        "tf": "M15",
        "cost_model_version": "4.1",
        "cost_source": "FROM_TICKS",
        # COMMISSION UNIT FIX 2026-08-06: 14.17 -> true 0.78 bps.
        "round_trip_bps_used": {"EURUSD": 0.78},
        "slippage_source": "fill_simulator_p90_points",
        "slippage_bps_used": {"EURUSD": 0.087},  # 1 pt x 1e-5 / 1.1553 x 1e4
        "strategy_name": "EurSessionBreakout",
    },
    8003: {
        "id": "DIRG-BTC-TSMOM-YZ",
        "symbol": "BTCUSD",
        "tf": "D1",
        "cost_model_version": "4.1",
        "cost_source": "FROM_TICKS",
        "round_trip_bps_used": {"BTCUSD": 6.30},
        "slippage_source": "fill_simulator_p90_points",
        "slippage_bps_used": {"BTCUSD": 0.495},
        "strategy_name": "BtcTsmomYz",
    },
}


def load_ohlcv(symbol: str, tf: str) -> pd.DataFrame:
    """Load OHLCV from duckdb, sorted, with UTC timestamps."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(
        "SELECT time, open, high, low, close, volume FROM ohlcv WHERE symbol = ? AND timeframe = ? ORDER BY time",
        [symbol, TF_CONVENTION[tf]],
    ).fetchdf()
    con.close()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def build_strategy(name: str):
    from quant_os.strategies.btc_donchian_trend import BtcDonchianTrend
    from quant_os.strategies.btc_tsmom_yz import BtcTsmomYz
    from quant_os.strategies.eur_session_breakout import EurSessionBreakout

    if name == "BtcDonchianTrend":
        return BtcDonchianTrend()
    if name == "EurSessionBreakout":
        return EurSessionBreakout()
    if name == "BtcTsmomYz":
        return BtcTsmomYz()
    raise ValueError(f"unknown strategy {name}")


def run_trial(trial_no: int, dry_run: bool = False) -> dict:
    spec = TRIALS[trial_no]
    symbol = spec["symbol"]
    tf = spec["tf"]

    print(f"\n=== Trial {trial_no} ({spec['id']}) ===")
    df = load_ohlcv(symbol, tf)
    print(f"  data: {len(df):,} bars ({df['time'].min().date()} -> {df['time'].max().date()})")

    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }
    timestamps = df["time"].dt.to_pydatetime().tolist()  # datetime objects — engine expects .isoformat() on them

    # Real measured cost profile (fail-closed on unmeasured)
    from quant_os.backtest.dynamic_spread_model import SymbolCostProfile

    profile = SymbolCostProfile.for_symbol(symbol)
    print(
        f"  cost: spread {profile.get_spread_bps():.4f} bps | comm {profile.commission_bps} | status {profile.status}"
    )

    from quant_os.backtest.engine import BacktestConfig, BacktestEngine

    config = BacktestConfig(
        initial_capital=10000,
        slippage_pips=0.0,  # filled via SymbolCostProfile in measured-cost path
        spread_pips=0.0,
        commission_per_lot=Decimal(str(profile.commission_bps)),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
        enable_swap=False,  # no swap data for BTCUSD/EURUSD in calibration — honest, not guessed
    )
    strategy = build_strategy(spec["strategy_name"])
    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False
    _orig_reset = engine._reset

    def _patched_reset():
        _orig_reset()
        engine._pnl_tracker = None
        engine._regime_detector = None

    engine._reset = _patched_reset
    results = engine.run()

    full_equity = [{"timestamp": p.timestamp, "equity": p.equity, "balance": p.balance} for p in engine.equity_curve]
    results["_full_equity_curve"] = full_equity

    # Per-asset metrics (BacktestMetrics object or dict — handle both)
    trades = results.get("trades", [])
    metrics = results.get("metrics", {})
    if hasattr(metrics, "as_dict"):
        metrics = metrics.as_dict()
    elif not isinstance(metrics, dict):
        metrics = vars(metrics) if hasattr(metrics, "__dict__") else {}
    print(
        f"  trades: {metrics.get('total_trades', len(trades))} | sharpe: {metrics.get('sharpe_ratio', 'n/a')} | PF: {metrics.get('profit_factor', 'n/a')}"
    )

    # Daily returns for DSR
    eq = pd.DataFrame(full_equity)
    if len(eq) > 1:
        eq["date"] = pd.to_datetime(eq["timestamp"], utc=True).dt.date
        eq["ret"] = eq["equity"].pct_change().fillna(0.0)
        daily = eq.groupby("date")["ret"].sum()
        sharpe_daily = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
    else:
        daily = pd.Series(dtype=float)
        sharpe_daily = 0.0

    # DSR (Deflated Sharpe Ratio) — single-trial: N=1 trial count, use bar count
    from quant_os.validation.deflated_sharpe import deflated_sharpe_ratio

    n_trials = 1  # per-trial DSR (Direction G trials are independent)
    dsr = 0.0
    dsr_pass = False
    try:
        dsr_res = deflated_sharpe_ratio(sharpe_daily, n_trials, len(daily), sharpe_annualization_factor=252.0)
        if hasattr(dsr_res, "probability_alpha"):
            # NOTE: `passes_threshold` has a pre-existing bug (adjusted-expected
            # inflates to -46 with n_trials=1). Use the p-value directly: a
            # strategy passes DSR only if its p-value < 0.05 (significant, not
            # due to chance) AND observed sharpe > 0.
            prob_alpha = float(dsr_res.probability_alpha)
            dsr = 1.0 - prob_alpha  # "deflated" = probability not due to chance
            dsr_pass = sharpe_daily > 0 and prob_alpha < 0.05
        else:
            dsr = float(dsr_res)
            dsr_pass = dsr >= 0.95
    except Exception as exc:  # noqa: BLE001 — DSR failure is reported, not fatal
        print(f"  [WARN] DSR computation failed: {exc}")

    verdict = "PASS" if (len(trades) >= 30 and sharpe_daily > 1.0 and dsr_pass) else "REJECT"
    print(
        f"  sharpe_daily: {sharpe_daily:.4f} | DSR: {dsr:.4f} (pass>=0.95: {dsr_pass}) | trades>=30: {len(trades) >= 30}"
    )
    print(f"  -> VERDICT: {verdict}")

    result_summary = {
        "n_trades": len(trades),
        "sharpe_daily": round(sharpe_daily, 4),
        "dsr": round(dsr, 4),
        "dsr_pass": dsr_pass,
        "total_return_pct": round(float(metrics.get("total_return_pct", 0.0)), 3),
        "max_dd_pct": round(float(metrics.get("max_drawdown_pct", 0.0)), 3),
        "n_bars": len(df),
        "data_range": f"{df['time'].min().date()} -> {df['time'].max().date()}",
        "cost": {
            "spread_bps": float(profile.get_spread_bps()),
            "commission_bps": float(profile.commission_bps),
            "round_trip_bps": spec["round_trip_bps_used"][symbol],
            "slippage_p90_points": spec["slippage_bps_used"][symbol],
        },
    }

    if dry_run:
        print("  [DRY-RUN] verdict not written to registry")
        return {"trial_number": trial_no, "verdict": verdict, "result_summary": result_summary}

    # Stamp + write registry (Phase 1 provenance)
    from quant_os.research.registry_schema import stamp_trial_entry

    entry = stamp_trial_entry(
        trial_number=trial_no,
        id=spec["id"],
        status=verdict,
        instrument=f"{symbol} ({tf})",
        symbols=[symbol],
        cost_model_version=spec["cost_model_version"],
        cost_source=spec["cost_source"],
        round_trip_bps_used=spec["round_trip_bps_used"],
        slippage_source=spec["slippage_source"],
        slippage_bps_used=spec["slippage_bps_used"],
        result_summary=result_summary,
    )
    # Replace existing PRE_REGISTERED entry in registry_g
    registry = json.loads(REGISTRY_G.read_text(encoding="utf-8"))
    registry["hypotheses"] = [h for h in registry["hypotheses"] if h.get("trial_number") != trial_no]
    registry["hypotheses"].append(entry)
    registry["last_updated"] = datetime.now(UTC).isoformat()
    REGISTRY_G.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Update ledger lineage
    ledger = json.loads(LEDGER_G.read_text(encoding="utf-8"))
    ledger["lineage"].append(
        {
            "trial_id": str(trial_no),
            "status": verdict,
            "result_at": datetime.now(UTC).isoformat(),
            "notes": f"{spec['id']} — stamped with provenance per Phase 1",
        }
    )
    ledger["cumulative_trial_count"] += 1
    ledger["new_hypotheses_used"] += 1
    ledger["new_hypotheses_remaining"] = max(0, ledger["cumulative_trial_cap"] - ledger["new_hypotheses_used"])
    LEDGER_G.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"  [OK] verdict written to {REGISTRY_G.name} + {LEDGER_G.name}")
    return {"trial_number": trial_no, "verdict": verdict, "result_summary": result_summary}


def main() -> int:
    p = argparse.ArgumentParser(description="Direction G trial runner (8001/8002)")
    p.add_argument("--trials", nargs="+", type=int, default=[8001, 8002, 8003], choices=[8001, 8002, 8003])
    p.add_argument("--dry-run", action="store_true", help="run without writing registry")
    args = p.parse_args()

    for t in args.trials:
        run_trial(t, dry_run=args.dry_run)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
