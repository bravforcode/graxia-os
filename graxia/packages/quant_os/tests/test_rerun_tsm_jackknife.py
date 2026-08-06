# tests/test_rerun_tsm_jackknife.py
"""Robustness test for the closure rerun script (review finding #7):
compute_metrics can return {"name": ...} without 'sharpe' for short series;
main() must not crash with KeyError and must still emit a verdict."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import rerun_tsm_jackknife as rj


def test_main_survives_metrics_without_sharpe(tmp_path, monkeypatch):
    # fake the whole pipeline with a short-series compute_metrics
    import pandas as pd

    def fake_load_data():
        return pd.DataFrame()

    def fake_get_close_matrix(data):
        return pd.DataFrame({"XAUUSD": [1.0, 2.0], "BTC_YF": [1.0, 3.0]})

    def fake_portfolio_backtest(close, lookbacks, target_vol, cost_bps):
        import pandas as pd

        return pd.Series([0.001] * 50), {}, {}

    def fake_compute_metrics(ret, name):
        # short series: returns name only, NO 'sharpe' key
        return {"name": name}

    monkeypatch.setattr(rj, "load_data", fake_load_data)
    monkeypatch.setattr(rj, "get_close_matrix", fake_get_close_matrix)
    monkeypatch.setattr(rj, "portfolio_backtest", fake_portfolio_backtest)
    monkeypatch.setattr(rj, "compute_metrics", fake_compute_metrics)
    out = tmp_path / "rerun.json"
    monkeypatch.setattr(rj, "OUT_PATH", out)

    assert rj.main() == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["verdict"] in {"REJECT_CONFIRMED", "INCONCLUSIVE"}
    assert "sharpe" in d["baseline"] or d["baseline"].get("sharpe", 0.0) == 0.0
