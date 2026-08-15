"""
Tests for validation/instrument_selection.py -- the Phase 3 multi-instrument
selection layer.

Covers:
  - Guard clauses: missing cost data / missing OHLCV data never select.
  - The actual bug this module fixes: with N simultaneous instruments,
    a naive per-instrument significance threshold (as used by
    scripts/run_multi_instrument_wf.py::determine_verdict) produces
    spurious "significant" results from pure noise; Benjamini-Hochberg
    correction must suppress those false positives while still selecting
    a genuine planted edge.
"""

from __future__ import annotations

from validation.instrument_selection import select_instruments

# ---------------------------------------------------------------------------
# Helpers -- synthetic run_wf_fn results, no real data/model training needed
# (the statistics under test operate on the aggregate dict, not on how it
# was produced -- see tests/test_auto_retrain.py for the real-model-training
# style test used at the evaluate_model layer instead).
# ---------------------------------------------------------------------------


def _wf_result(
    symbol: str, t_stat: float, n_folds: int = 10, total_trades: int = 100, net_positive: bool = True
) -> dict:
    positive_folds = n_folds if net_positive else 0
    return {
        "symbol": symbol,
        "status": "OK",
        "t_statistic": t_stat,
        "n_folds": n_folds,
        "total_trades": total_trades,
        "total_net_pnl": 100.0 if net_positive else -100.0,
        "positive_folds": positive_folds,
    }


def _always_present_costs(_symbol: str) -> dict:
    return {"spread": 1e-5, "slippage": 3e-5}


class TestSelectInstrumentsGuards:
    def test_missing_cost_data_never_selects(self):
        result = select_instruments(
            ["XAUUSD"],
            load_ohlcv_fn=lambda s: [0],  # non-empty stand-in; run_wf_fn ignores its content
            cost_lookup_fn=lambda s: None,  # no real cost data
            run_wf_fn=lambda **kw: _wf_result(kw["symbol"], t_stat=10.0),
        )
        assert result.selected_symbols == []
        assert result.evaluations[0].status == "NO_COST_DATA"

    def test_missing_ohlcv_data_never_selects(self):
        result = select_instruments(
            ["XAUUSD"],
            load_ohlcv_fn=lambda s: None,
            cost_lookup_fn=_always_present_costs,
            run_wf_fn=lambda **kw: _wf_result(kw["symbol"], t_stat=10.0),
        )
        assert result.selected_symbols == []
        assert result.evaluations[0].status == "NO_DATA"

    def test_below_min_trades_never_selects_even_if_significant(self):
        def run_wf(**kw):
            return _wf_result(kw["symbol"], t_stat=10.0, total_trades=5)  # huge t-stat, tiny sample

        result = select_instruments(
            ["XAUUSD"],
            load_ohlcv_fn=lambda s: [0],  # non-empty stand-in; run_wf_fn ignores its content
            cost_lookup_fn=_always_present_costs,
            run_wf_fn=run_wf,
            min_trades=30,
        )
        assert result.selected_symbols == []


class TestBenjaminiHochbergCorrectionActuallyMatters:
    """The behavioral proof this module exists: a naive per-instrument
    threshold and a BH-corrected one must disagree on a batch containing
    mostly noise plus one real edge -- and the corrected version must be
    the one that ships."""

    def test_naive_threshold_would_false_positive_on_pure_noise_batch(self):
        """20 instruments, all pure noise (t-stats drawn to straddle the
        classic |t|>=2 'significance' folklore threshold). A naive,
        uncorrected per-instrument gate at |t|>=2 falsely flags several of
        these as significant purely from the multiple-comparisons effect --
        this reproduces the exact bug in
        scripts/run_multi_instrument_wf.py::determine_verdict()."""
        import numpy as np

        rng = np.random.default_rng(7)
        noise_t_stats = rng.normal(0, 1.0, 20) * 1.3  # centered on 0, some will exceed 2 by chance

        naive_false_positives = sum(1 for t in noise_t_stats if abs(t) >= 2.0)
        assert naive_false_positives >= 1, "test setup should reproduce at least one naive false positive"

        symbols = [f"NOISE{i}" for i in range(20)]

        def run_wf(**kw):
            idx = symbols.index(kw["symbol"])
            return _wf_result(kw["symbol"], t_stat=float(noise_t_stats[idx]), net_positive=noise_t_stats[idx] > 0)

        result = select_instruments(
            symbols,
            load_ohlcv_fn=lambda s: [0],  # non-empty stand-in; run_wf_fn ignores its content
            cost_lookup_fn=_always_present_costs,
            run_wf_fn=run_wf,
            alpha=0.05,
        )

        # BH correction across the batch must suppress the naive false
        # positives that a per-instrument-only threshold would have kept.
        assert result.selected_symbols == []

    def test_genuine_planted_edge_still_selected_among_noise(self):
        """19 noise instruments (small t-stats) plus 1 with a strong,
        genuine edge (large t-stat, many folds/trades) -- BH correction
        must still let the real signal through, it isn't a blanket veto."""
        import numpy as np

        rng = np.random.default_rng(11)
        noise_t_stats = rng.normal(0, 0.5, 19)  # small, non-significant noise
        symbols = [f"NOISE{i}" for i in range(19)] + ["REALEDGE"]
        t_stats = list(noise_t_stats) + [8.0]  # REALEDGE: strong, real signal

        def run_wf(**kw):
            idx = symbols.index(kw["symbol"])
            t = t_stats[idx]
            return _wf_result(kw["symbol"], t_stat=float(t), n_folds=20, total_trades=200, net_positive=t > 0)

        result = select_instruments(
            symbols,
            load_ohlcv_fn=lambda s: [0],  # non-empty stand-in; run_wf_fn ignores its content
            cost_lookup_fn=_always_present_costs,
            run_wf_fn=run_wf,
            alpha=0.05,
            min_trades=30,
        )

        assert result.selected_symbols == ["REALEDGE"]
