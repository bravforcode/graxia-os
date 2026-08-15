"""Phase 3 — Multi-Instrument Selection Layer (statistics + orchestration).

Given a candidate universe, runs the canonical walk-forward engine per
instrument with real costs, derives a p-value from each instrument's
fold-level t-statistic, and applies Benjamini-Hochberg correction across
the whole batch before deciding what actually gets selected.

This exists because scripts/run_multi_instrument_wf.py's
determine_verdict() applies a raw, uncorrected per-instrument t-stat
threshold (abs(t_stat) >= 1.5) independently across up to 14 instruments.
With N simultaneous naive tests, spurious PROMOTE verdicts are *expected*
from noise alone -- this is the "A5" gap documented in
reports/go_live_gate_corrected_sequencing.md.
validation.multiple_testing.benjamini_hochberg() already exists and is
correct; it was just never wired into a selection decision. This module
does that wiring, it does not reimplement the correction itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from scipy import stats

from .multiple_testing import benjamini_hochberg


@dataclass
class InstrumentEvaluation:
    """Evidence for one candidate symbol, including the correction outcome."""

    symbol: str
    status: str  # "OK" | "NO_DATA" | "NO_COST_DATA" | "INSUFFICIENT_DATA" | "ERROR: ..."
    t_stat: float = 0.0
    n_folds: int = 0
    total_trades: int = 0
    raw_p_value: float = 1.0
    adjusted_p_value: float = 1.0
    stable: bool = False
    selected: bool = False


@dataclass
class SelectionResult:
    alpha: float
    min_trades: int
    evaluations: list[InstrumentEvaluation] = field(default_factory=list)

    @property
    def selected_symbols(self) -> list[str]:
        """The honest (possibly empty) list of instruments that cleared
        every gate: BH-adjusted significance, fold-stability, and a
        minimum trade-count floor."""
        return [e.symbol for e in self.evaluations if e.selected]


def _two_sided_p_value(t_stat: float, dof: int) -> float:
    """Two-sided p-value for a t-statistic with `dof` degrees of freedom."""
    if dof <= 0:
        return 1.0
    return float(2.0 * stats.t.sf(abs(t_stat), dof))


def select_instruments(
    candidates: list[str],
    load_ohlcv_fn: Callable[[str], Any],
    cost_lookup_fn: Callable[[str], dict | None],
    run_wf_fn: Callable[..., dict],
    *,
    timeframe: str = "H1",
    alpha: float = 0.05,
    min_trades: int = 30,
) -> SelectionResult:
    """Evaluate each candidate via the canonical walk-forward engine, then
    decide selection using Benjamini-Hochberg-corrected significance --
    not a naive per-instrument threshold.

    Args:
        candidates: symbols to evaluate (the cost-verified universe).
        load_ohlcv_fn: symbol -> OHLCV DataFrame, or None/empty if
            unavailable.
        cost_lookup_fn: symbol -> {"spread": float, "slippage": float}, or
            None if no real cost data exists for that symbol. Fail loud
            (skip, don't fabricate a cost), same discipline already
            applied in scripts/run_multi_instrument_wf.py.
        run_wf_fn: (symbol, timeframe, df, spread_cost, slippage_p90) -> dict
            with at least {"status", "t_statistic", "n_folds",
            "total_trades", "total_net_pnl", "positive_folds"} on success
            (matches scripts/run_multi_instrument_wf.py::run_wf_single).
        alpha: false discovery rate for BH correction.
        min_trades: minimum OOS trades required, independent of
            significance -- guards against a "significant" result built
            on a handful of trades.

    Returns:
        SelectionResult with every candidate's evidence and the final
        (possibly empty) selected list.
    """
    raw_results: list[dict] = []

    for symbol in candidates:
        costs = cost_lookup_fn(symbol)
        if not costs:
            raw_results.append({"symbol": symbol, "status": "NO_COST_DATA"})
            continue

        df = load_ohlcv_fn(symbol)
        if df is None or len(df) == 0:
            raw_results.append({"symbol": symbol, "status": "NO_DATA"})
            continue

        result = run_wf_fn(
            symbol=symbol,
            timeframe=timeframe,
            df=df,
            spread_cost=costs["spread"],
            slippage_p90=costs["slippage"],
        )
        raw_results.append(result)

    # A p-value for every OK result with >1 fold; everything else gets
    # p=1.0 so it can never clear the alpha threshold below.
    p_values: list[float] = []
    for r in raw_results:
        if r.get("status") == "OK" and r.get("n_folds", 0) > 1:
            p_values.append(_two_sided_p_value(r.get("t_statistic", 0.0), r["n_folds"] - 1))
        else:
            p_values.append(1.0)

    _, adjusted = benjamini_hochberg(p_values, alpha=alpha)

    evaluations: list[InstrumentEvaluation] = []
    for r, raw_p, adj_p in zip(raw_results, p_values, adjusted, strict=True):
        status = r.get("status", "UNKNOWN")
        ok = status == "OK"
        n_folds = r.get("n_folds", 0)
        positive_folds = r.get("positive_folds", 0)
        total_net = r.get("total_net_pnl", 0)
        total_trades = r.get("total_trades", 0)

        # Same "stable" definition as validation.walk_forward.run_walk_forward's
        # own aggregate.stable: more than half the folds positive AND net positive.
        stable = bool(ok and n_folds > 0 and positive_folds > n_folds / 2 and total_net > 0)
        selected = bool(ok and adj_p <= alpha and stable and total_trades >= min_trades)

        evaluations.append(
            InstrumentEvaluation(
                symbol=r["symbol"],
                status=status,
                t_stat=float(r.get("t_statistic", 0.0)),
                n_folds=n_folds,
                total_trades=total_trades,
                raw_p_value=round(float(raw_p), 6),
                adjusted_p_value=round(float(adj_p), 6),
                stable=stable,
                selected=selected,
            )
        )

    return SelectionResult(alpha=alpha, min_trades=min_trades, evaluations=evaluations)
