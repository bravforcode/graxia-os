"""P4 screening runner for Direction I (spec §5 P4).

For each shortlist candidate: resolve strategy -> register_config (N, BEFORE
run) -> run BacktestEngine with conservative costs (cost_stress=True, measured
profile) -> capture LookaheadGuard -> assert zero violations -> record result.
Survivors: sharpe_ratio > 0 AND total_trades >= 30.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from decimal import Decimal
from pathlib import Path

# Monorepo import bootstrap (same as scripts/run_direction_g_trials.py).
ROOT = Path(__file__).resolve().parent.parent
_GRAXIA_ROOT = ROOT.parent.parent
_MONOREPO_ROOT = _GRAXIA_ROOT.parent
for _p in (_MONOREPO_ROOT, _GRAXIA_ROOT, ROOT.parent, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import quant_os.backtest.engine as bt_engine  # noqa: E402  (guard patching target)
from quant_os.backtest.dynamic_spread_model import SymbolCostProfile  # noqa: E402
from quant_os.backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from quant_os.research.screening_map import resolve_candidate  # noqa: E402
from quant_os.research.screening_registry import register_config, update_config_status  # noqa: E402
from quant_os.scripts.screening_guard import assert_no_guard_violations  # noqa: E402

DB_PATH = ROOT / "data" / "market_data.duckdb"
TF_CONVENTION = {
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
    "W1": "1w",
    "MN1": "1mo",
}
MIN_TRADES = 30
MIN_SHARPE = 0.0


class TrackingGuard(bt_engine.LookaheadGuard):
    instances: list = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.instances.append(self)


def load_ohlcv(symbol: str, tf: str) -> pd.DataFrame | None:
    if tf not in TF_CONVENTION:
        return None
    # CSV first: data/{SYM}_{TF}.csv covers ALL timeframes (duckdb is partial)
    csv_path = ROOT / "data" / f"{symbol}_{tf}.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            df["time"] = pd.to_datetime(df["time"], utc=True)
            df = df.sort_values("time")
            return df
        except Exception:
            return None
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            "SELECT time, open, high, low, close, volume FROM ohlcv "
            "WHERE symbol = ? AND timeframe = ? ORDER BY time",
            [symbol, TF_CONVENTION[tf]],
        ).fetchdf()
    except Exception:
        return None
    finally:
        con.close()
    if df.empty:
        return None
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def run_candidate(entry: dict, config_id: str, years: int) -> dict:
    resolved = resolve_candidate(entry)
    if resolved["status"] != "ok":
        return {"config_id": config_id, "status": "no_strategy", "reason": resolved.get("reason", "")}
    symbol = entry.get("symbol", "")
    tf = resolved["timeframe"]
    df = load_ohlcv(symbol, tf)
    if df is None:
        return {"config_id": config_id, "status": "no_cost_data", "reason": f"no {symbol} {tf} data in duckdb"}
    try:
        profile = SymbolCostProfile.for_symbol(symbol)
    except Exception as exc:  # noqa: BLE001 — UnmeasuredCostError etc.
        return {"config_id": config_id, "status": "no_cost_data", "reason": str(exc)}
    # slippage null check: measured path would raise mid-run — classify honestly
    try:
        profile.get_slippage_bps()
    except Exception as exc:  # noqa: BLE001
        return {"config_id": config_id, "status": "no_slippage_data", "reason": str(exc)}
    ohlcv = {k: df[k].tolist() for k in ("open", "high", "low", "close", "volume")}
    timestamps = df["time"].dt.to_pydatetime().tolist()
    config = BacktestConfig(
        initial_capital=10000,
        slippage_pips=None,
        spread_pips=None,
        cost_stress=True,  # A1 conservative proxy: p95 spread
        commission_per_lot=Decimal(str(profile.commission_bps)),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
        enable_swap=False,
        start_date=dt.date.today() - dt.timedelta(days=365 * years),  # screening window (full history is for trials)
    )
    strategy = resolved["strategy_class"](**resolved["params"]) if resolved["params"] else resolved["strategy_class"]()
    TrackingGuard.instances = []
    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False
    results = engine.run()
    engine.guard = TrackingGuard.instances[-1] if TrackingGuard.instances else None
    assert_no_guard_violations(engine, config_id=config_id)  # fail-closed
    metrics = results.get("metrics")
    m = metrics.as_dict() if hasattr(metrics, "as_dict") else vars(metrics)
    out = {
        "config_id": config_id,
        "status": "done",
        "symbol": symbol,
        "timeframe": tf,
        "total_trades": m.get("total_trades", 0),
        "sharpe_ratio": m.get("sharpe_ratio", 0.0),
        "profit_factor": m.get("profit_factor", 0.0),
        "total_return_pct": m.get("total_return_pct", 0.0),
        "max_drawdown_pct": m.get("max_drawdown_pct", 0.0),
    }
    out["survivor"] = out["total_trades"] >= MIN_TRADES and out["sharpe_ratio"] > MIN_SHARPE
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--years", type=int, default=5, help="screening window years (trials use full history)")
    parser.add_argument(
        "--shortlist",
        default=str(ROOT / "research" / "catalog_i" / "shortlist_wave1.json"),
    )
    parser.add_argument("--out", default=str(ROOT / "research" / "catalog_i" / "screening_results.json"))
    parser.add_argument("--log", default=str(ROOT / "research" / "screening_log_i.json"))
    args = parser.parse_args(argv)

    bt_engine.LookaheadGuard = TrackingGuard
    # ENGINE BUG (audited 2026-08-06): when Phase-4 wiring is available
    # (_PHASE4_WIRING_AVAILABLE=True), run() re-creates _pnl_tracker on every
    # run and the per-bar loop takes the tracker branch, which NEVER appends to
    # equity_curve -> sharpe_ratio/sortino/max_drawdown_pct are silently 0.0.
    # Disabling the flag forces the _update_equity path so risk-adjusted
    # metrics are real. Affects ALL engine runs (incl. P6 trials) — engine-side
    # fix tracked separately.
    bt_engine._PHASE4_WIRING_AVAILABLE = False

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():  # crash-safe resume: keep metrics from a partial run
        try:
            results = json.loads(out_path.read_text(encoding="utf-8")).get("results", {})
        except (json.JSONDecodeError, OSError):
            results = {}

    shortlist = json.loads(Path(args.shortlist).read_text(encoding="utf-8")).get("shortlist", [])
    if args.limit > 0:
        shortlist = shortlist[: args.limit]

    survivors = []
    for idx, entry in enumerate(shortlist, 1):
        cfg = register_config(
            args.log,
            mechanism=entry.get("mechanism_family", entry.get("mechanism", "other")),
            symbol=entry.get("symbol", ""),
            timeframe=entry.get("timeframe", "ALL"),
            params=entry.get("params") or {},
            data_range=("", ""),
        )
        config_id = cfg["config_id"]
        if config_id in results:
            print(f"  [{idx}/{len(shortlist)}] RESUME skip {config_id}", flush=True)
            if results[config_id].get("survivor"):
                survivors.append({**entry, "screening": results[config_id]})
            continue
        try:
            res = run_candidate(entry, config_id, years=args.years)
        except Exception as exc:  # noqa: BLE001 — VOID + audit per spec
            res = {"config_id": config_id, "status": "VOID", "reason": str(exc)}
        update_config_status(args.log, config_id, res["status"])
        res["n_registered"] = True
        results[config_id] = res
        print(
            f"  [{idx}/{len(shortlist)}] {res['status']:<14} {res.get('symbol','?'):<8} "
            f"{res.get('timeframe','?'):<5} trades={res.get('total_trades','-'):<5} "
            f"sharpe={res.get('sharpe_ratio','-')}",
            flush=True,
        )
        if res.get("survivor"):
            survivors.append({**entry, "screening": res})
        # crash-safe: persist after every candidate
        Path(args.out).write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "direction": "I",
                    "configs_tried": len(results),
                    "survivors": survivors,
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    out = {
        "schema_version": "1.0",
        "direction": "I",
        "configs_tried": len(results),
        "survivors": survivors,
        "results": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"screening: {len(results)} configs, {len(survivors)} survivors -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
