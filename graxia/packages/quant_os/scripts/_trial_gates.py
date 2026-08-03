"""Institutional robustness gates for trial harnesses (SP2).

WFA (purged-CV) + Bootstrap CI + MinBTL.
PBO is intentionally NOT computed: WS-A trials are single frozen-config
pre-registrations with no parameter search space; PBO would measure search
bias that does not exist, and fabricating variants post-hoc would introduce
selection bias. Recorded as N/A with this reason.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel: str):
    import sys

    spec = importlib.util.spec_from_file_location(mod_name, str(_ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod  # required: @dataclass fields resolve via sys.modules (Py3.12)
    spec.loader.exec_module(mod)
    return mod


def run_institutional_gates(
    portfolio_returns: pd.Series,
    returns_by_symbol: dict[str, pd.Series],
    observed_sharpe: float,
    n_trials: int,
    n_bars: int,
    annualization_factor: float = 252,
) -> dict:
    """Compute WFA + Bootstrap CI + MinBTL for a trial harness.

    Args:
        portfolio_returns: Daily portfolio return series.
        returns_by_symbol: symbol -> daily signal-aligned returns.
        observed_sharpe: ANNUALIZED Sharpe of the portfolio.
        n_trials: Reconciled cumulative trial count (multiple testing).
        n_bars: Bar count (current observations for MinBTL).
        annualization_factor: Bars per year (252 for D1).

    Returns:
        dict with keys: wfa, bootstrap_ci, min_btl, pbo_na, combined_pass.
    """
    wf = _load("_wf", "validation/walk_forward.py")
    bs = _load("_bs", "validation/bootstrap_sensitivity.py")
    dsr = _load("_dsr", "validation/deflated_sharpe.py")

    # ── WFA: purged-CV time-split robustness of the signal ──────────────
    wfa_result: dict = {"n_folds": 0, "fold_sharpes": [], "oos_sharpe_mean": 0.0, "oos_sharpe_std": 0.0, "pass": False}
    n = len(portfolio_returns)
    if n >= 200:
        folds = list(wf.purged_cv(n, n_folds=5, embargo=12))
        fold_sharpes = []
        for _tr_idx, te_idx in folds:
            if len(te_idx) < 30:
                continue
            fold_ret = portfolio_returns.iloc[te_idx]
            sd = float(fold_ret.std())
            if sd > 0:
                fold_sharpes.append(float(fold_ret.mean() / sd * math.sqrt(annualization_factor)))
        if fold_sharpes:
            arr = np.array(fold_sharpes)
            wfa_result = {
                "n_folds": len(fold_sharpes),
                "fold_sharpes": [round(x, 4) for x in fold_sharpes],
                "oos_sharpe_mean": round(float(arr.mean()), 4),
                "oos_sharpe_std": round(float(arr.std(ddof=1)), 4),
                "pass": float(arr.mean()) > 0,
            }

    # ── Bootstrap CI on portfolio Sharpe ────────────────────────────────
    boot_result = {"lower": 0.0, "upper": 0.0, "pass": False}
    if len(portfolio_returns) >= 100:
        boot = bs.bootstrap_confidence_interval(
            portfolio_returns.tolist(), n_resamples=1000, confidence_level=0.95, seed=42
        )
        boot_result = {
            "lower": round(float(boot.confidence_interval_95[0]), 6),
            "upper": round(float(boot.confidence_interval_95[1]), 6),
            "pass": bool(boot.passes_threshold),
        }

    # ── MinBTL ──────────────────────────────────────────────────────────
    min_btl = dsr.min_backtest_length(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        sharpe_annualization_factor=math.sqrt(annualization_factor),
        current_observations=n_bars,
    )
    min_btl_result = {
        "min_observations": int(min_btl.min_observations),
        "sufficient": bool(min_btl.sufficient),
        "pass": bool(min_btl.sufficient),
    }

    pbo_na = {
        "value": None,
        "pass": None,
        "reason": (
            "PBO not applicable: WS-A trials are single frozen-config pre-registrations "
            "(no parameter search space). PBO measures search bias which does not exist; "
            "fabricating variants post-hoc would introduce selection bias."
        ),
    }

    gate_passes = [wfa_result["pass"], boot_result["pass"], min_btl_result["pass"]]
    return {
        "wfa": wfa_result,
        "bootstrap_ci": boot_result,
        "min_btl": min_btl_result,
        "pbo_na": pbo_na,
        "combined_pass": bool(sum(gate_passes) >= 2),
        "status": "OK",
    }
