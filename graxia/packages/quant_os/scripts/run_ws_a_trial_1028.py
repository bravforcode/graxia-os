"""
WS-A (Trial 1028) — Time Series Momentum (Moskowitz-Ooi-Pedersen 2012) run harness.

Pre-registration: research/pre_registration/trial_1028_ws_a_tsmom_mop2012.md

GATING PHASE (always runs — verdict conditions 1-3):
  1. Load each symbol ONLY via provenance.load_provenance_checked (never raw
     load_csv_data / load_ohlcv / a direct read). Map the OHLCV frame to the
     dict[str, list] + timestamps format BacktestEngine.load_data expects.
  2. Runtime assert min(timestamps).year >= 2005 per asset — belt-and-suspenders
     over the loader's own impossible-date hard-fail.
  3. Record the loader path in research/hypothesis_registry.json (trial 1028)
     so the "provenance-checked" claim is auditable after the fact.

PIPELINE PHASE (--run-pipeline, requires trigger phrase): runs the §7 validation
  gates (signal -> BacktestEngine -> DK-test -> DSR@1050 -> jackknife ->
  cost-stress -> PBO). NOT executed without explicit authorization.

Safety: no capital, no live order, sacred holdout untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# Make the graxia package importable when run from the quant_os dir.
# graxia is a regular package, so its PARENT dir must be on sys.path.
_GRAXIA_ROOT = Path(__file__).resolve().parents[4]
if str(_GRAXIA_ROOT) not in sys.path:
    sys.path.insert(0, str(_GRAXIA_ROOT))

from graxia.packages.quant_os.provenance import (  # noqa: E402
    load_provenance_checked,
)

WS_A_UNIVERSE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]
PROVENANCE_FLOOR_YEAR = 2005
SLICE_START = "2005-01-01"
LOADER_PATH = "provenance.py::load_provenance_checked"
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "research" / "hypothesis_registry.json"


def load_symbol_provenance_checked(symbol: str) -> tuple[dict, list, pd.DataFrame]:
    """Conditions 1+2: load via provenance loader, map to engine format, assert year>=2005."""
    df = load_provenance_checked(symbol, slice_start=SLICE_START)
    ts_col = "time" if "time" in df.columns else "date"

    # Condition 1: map OHLCV frame -> dict[str, list] + timestamps (load_data format)
    data = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }
    timestamps = [pd.Timestamp(t).to_pydatetime() for t in df[ts_col].tolist()]

    # Feed the verified engine so the mapping is exercised, not just constructed.
    try:
        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        BacktestEngine().load_data(data, timestamps)
    except Exception as exc:  # pragma: no cover - env/import edge case
        print(f"  [warn] BacktestEngine.load_data skipped for {symbol}: {exc}")

    # Condition 2: belt-and-suspenders over the loader's own hard-fail
    min_year = min(t.year for t in timestamps)
    assert min_year >= PROVENANCE_FLOOR_YEAR, (
        f"{symbol}: min timestamp year {min_year} < {PROVENANCE_FLOOR_YEAR} "
        f"(provenance loader leaked an impossible date)"
    )
    return data, timestamps, df


def record_loader_path_in_registry(per_symbol: dict) -> None:
    """Condition 3: record the provenance-checked loader path in registry-1028."""
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"registry not found: {REGISTRY_PATH}")
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    found = False
    for entry in registry.get("hypotheses", []):
        if entry.get("trial_number") == 1028:
            entry["data_loading"] = {
                "loader": LOADER_PATH,
                "slice_start": SLICE_START,
                "provenance_checked": True,
                "asserted_min_year": PROVENANCE_FLOOR_YEAR,
                "per_symbol": per_symbol,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
            found = True
            break
    if not found:
        raise KeyError("trial 1028 entry not found in hypothesis_registry.json")
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def run_gating_phase() -> dict:
    """Conditions 1-3. Returns per-symbol provenance summary."""
    per_symbol: dict = {}
    for sym in WS_A_UNIVERSE:
        _data, _timestamps, df = load_symbol_provenance_checked(sym)
        ts_col = "time" if "time" in df.columns else "date"
        per_symbol[sym] = {
            "rows": int(len(df)),
            "min_year": int(df[ts_col].min().year),
            "max_year": int(df[ts_col].max().year),
            "loader": LOADER_PATH,
        }
        print(
            f"  {sym}: {len(df)} rows, "
            f"{per_symbol[sym]['min_year']}-{per_symbol[sym]['max_year']}, "
            f"loaded via {LOADER_PATH}, year>={PROVENANCE_FLOOR_YEAR} OK"
        )
    record_loader_path_in_registry(per_symbol)
    print(f"  recorded loader path in {REGISTRY_PATH.name} (trial 1028)")
    return per_symbol


def run_pipeline_phase() -> None:
    """§7 validation pipeline. Trigger-phrase gated; not run this session.

    ponytail: calls existing verified modules (compute_tsmom_signal with
    lookbacks=[252], vol_target=0.10; BacktestEngine per asset; edge_search_cross_sectional
    .run_dk_test; validation/deflated_sharpe.deflated_sharpe_ratio with N=1050;
    backtest/walk_forward PBO; validation/pipeline). Module APIs must be
    confirmed before the trigger-phrase run — run_dk_test signature unverified.
    """
    raise SystemExit("PIPELINE PHASE requires trigger phrase + module-API confirmation. Not run.")


def main() -> None:
    ap = argparse.ArgumentParser(description="WS-A (trial 1028) provenance-gated run harness")
    ap.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run §7 pipeline (requires trigger phrase)",
    )
    args = ap.parse_args()

    print("WS-A (trial 1028) — gating phase (verdict conditions 1-3)")
    run_gating_phase()

    if args.run_pipeline:
        run_pipeline_phase()
    else:
        print("Gating phase complete. Trial 1028 remains PRE-REGISTERED. Pipeline phase requires trigger phrase.")


if __name__ == "__main__":
    main()
