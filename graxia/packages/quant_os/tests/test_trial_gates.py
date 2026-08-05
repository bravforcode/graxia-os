"""Tests for _trial_gates.run_institutional_gates (SP2)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_trial_gates", str(_ROOT / "scripts" / "_trial_gates.py"))
_tg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tg)


def _make_returns(seed: int = 42, n: int = 1500, n_syms: int = 3) -> tuple[pd.Series, dict[str, pd.Series]]:
    rng = np.random.default_rng(seed)
    d = {f"s{i}": pd.Series(rng.normal(0.0004, 0.01, n)) for i in range(n_syms)}
    port = pd.concat(d.values(), axis=1).mean(axis=1)
    return port, d


def test_gates_return_expected_keys():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    assert set(["wfa", "bootstrap_ci", "min_btl", "pbo_na"]).issubset(r.keys())
    assert r["pbo_na"]["reason"]  # non-empty reason string


def test_wfa_has_folds():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    # purged_cv(n=1500, n_folds=5) yields 4 usable folds (fold_size=n//6=250, last unused)
    assert r["wfa"]["n_folds"] >= 3
    assert "oos_sharpe_mean" in r["wfa"]
    assert len(r["wfa"]["fold_sharpes"]) == r["wfa"]["n_folds"]


def test_bootstrap_ci_structure():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    ci = r["bootstrap_ci"]
    assert ci["lower"] < ci["upper"]
    assert "pass" in ci


def test_min_btl_structure():
    port, syms = _make_returns()
    r = _tg.run_institutional_gates(port, syms, observed_sharpe=1.2, n_trials=1050, n_bars=len(port))
    mb = r["min_btl"]
    assert "min_observations" in mb
    assert "sufficient" in mb


def test_insufficient_data_does_not_crash():
    port = pd.Series(np.random.default_rng(1).normal(0, 0.01, 60))
    r = _tg.run_institutional_gates(port, {"s0": port}, observed_sharpe=0.5, n_trials=10, n_bars=60)
    assert "status" in r or r["wfa"]["n_folds"] <= 5
