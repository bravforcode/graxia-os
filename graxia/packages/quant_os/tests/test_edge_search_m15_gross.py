"""Tests for gross diagnostic reconstruction (post-mortem trials 1034/1035)."""

from __future__ import annotations

from graxia.packages.quant_os.scripts.edge_search_m15_scalper import (
    build_gross_artifact,
    gross_reconstruct,
)


def _trade(pnl, spread=0.0, eslip=0.0, xslip=0.0, fees=0.0, exit_time="2026-01-02T12:00:00Z"):
    return {
        "pnl": pnl,
        "entry_spread_cost": spread,
        "entry_slippage_cost": eslip,
        "exit_slippage_cost": xslip,
        "fees": fees,
        "exit_time": exit_time,
    }


def _asset_result(trades, first_bar="2026-01-01T00:00:00Z", last_bar="2026-02-01T00:00:00Z"):
    return {"trades": trades, "first_bar": first_bar, "last_bar": last_bar}


def test_gross_reconstruct_reconstruction_and_monotonicity():
    # Trade 1: net +5, costs 8 -> gross +13. Trade 2: net -12, costs 8 -> gross -4.
    # Net PF = 5/12 < 1; Gross PF = 13/4 > 1. Reconstruction turns the loss toward
    # breakeven, and gross_pf must always be >= net_pf.
    trades = [
        _trade(pnl=5.0, spread=4.0, eslip=2.0, xslip=2.0),
        _trade(pnl=-12.0, spread=4.0, eslip=2.0, xslip=2.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    assert res["gross_pf"] > 1.0
    assert res["classification"] == "cost_driven"
    assert res["gross_pf"] >= 5.0 / 12.0  # monotonicity: gross >= net
    assert res["n_trades"] == 2


def test_gross_reconstruct_break_even_mult():
    # sim_pnl(m) = gross - cost*m: (13-8m) / (4+8m) = 1 -> m = 0.5625
    trades = [
        _trade(pnl=5.0, spread=4.0, eslip=2.0, xslip=2.0),
        _trade(pnl=-12.0, spread=4.0, eslip=2.0, xslip=2.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    assert 0.0 < res["break_even_mult"] <= 1.0
    assert abs(res["break_even_mult"] - 0.5625) < 0.01
    assert abs(res["break_even_round_trip_bps"] - 15.0 * 0.5625) < 0.2


def test_gross_reconstruct_structural():
    # Both trades stay negative even after adding back costs: gross PF < 1.
    trades = [
        _trade(pnl=-10.0, spread=1.0, eslip=1.0, xslip=1.0),
        _trade(pnl=-15.0, spread=1.0, eslip=1.0, xslip=1.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    assert res["gross_pf"] < 1.0
    assert res["classification"] == "structural"
    assert res["break_even_mult"] == 0.0
    assert res["break_even_round_trip_bps"] == 0.0


def test_gross_reconstruct_no_losses_clamps_mult():
    # All gross positive -> PF = inf -> clamp break_even_mult at 1.0, cost_driven.
    trades = [
        _trade(pnl=2.0, spread=1.0),
        _trade(pnl=5.0, spread=1.0),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=10.0)
    assert res["classification"] == "cost_driven"
    assert res["break_even_mult"] == 1.0


def test_gross_reconstruct_empty_trades():
    res = gross_reconstruct(_asset_result([]), measured_round_trip_bps=15.0)
    assert res["classification"] == "no_trades"
    assert res["gross_pf"] == 0.0


def test_gross_reconstruct_costs_sharpe_keys_present():
    trades = [
        _trade(pnl=-2.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-02T12:00:00Z"),
        _trade(pnl=-3.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-03T12:00:00Z"),
        _trade(pnl=4.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-04T12:00:00Z"),
        _trade(pnl=6.0, spread=1.0, eslip=0.5, xslip=0.5, fees=1.0, exit_time="2026-01-05T12:00:00Z"),
    ]
    res = gross_reconstruct(_asset_result(trades), measured_round_trip_bps=15.0)
    for key in (
        "gross_sharpe_daily",
        "net_sharpe_daily",
        "cost_erosion_sharpe",
        "gross_win_pct",
        "gross_total_return_pct",
        "gross_monthly_pct",
        "measured_round_trip_bps",
    ):
        assert key in res


def test_build_gross_artifact_schema():
    trades = [
        _trade(pnl=-10.0, spread=1.0, eslip=1.0, xslip=1.0),
        _trade(pnl=-15.0, spread=1.0, eslip=1.0, xslip=1.0),
    ]
    ar = {
        "symbol": "XAUUSD",
        **{"trades": trades, "first_bar": "2026-01-01T00:00:00Z", "last_bar": "2026-02-01T00:00:00Z"},
    }
    art = build_gross_artifact([ar], {"XAUUSD": 15.0})
    assert art["meta"]["diagnostic_only"] is True
    assert art["meta"]["verdict_unchanged"] is True
    assert art["per_asset"]["XAUUSD"]["classification"] == "structural"
    assert art["break_even"]["XAUUSD"]["measured_round_trip_bps"] == 15.0
    assert art["summary"]["n_assets"] == 1
    assert art["summary"]["n_structural"] == 1
    assert art["summary"]["n_cost_driven"] == 0
