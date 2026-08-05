"""PaperAdapter swap-cost wiring (KNOWN_LIMITATIONS #3 live-path gap).

The backtest engine has always applied swap; the live/paper path did not —
`execution/swap_model.py` had zero call sites outside tests. These tests
verify the paper adapter now realizes swap on close using the SAME measured
rates as backtest (config/cost_calibration.json, bps of notional), and that
symbols without usable swap data fail closed (zero swap, never assumed).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from graxia.packages.quant_os.execution.adapters.paper import (
    PaperAdapter,
    _swap_rates_for,
)
from graxia.packages.quant_os.execution.adapters.base import Order
from graxia.packages.quant_os.execution.swap_model import (
    SwapMode,
    SwapPolicy,
    SwapRates,
)


def _order(symbol: str, side: str, quantity: float) -> Order:
    return Order(
        order_id=f"t-{symbol}-{side}-{quantity}",
        signal_id="",
        symbol=symbol,
        asset_class="",
        side=side,
        quantity=quantity,
    )


def test_swap_rates_oil_fixed():
    """OIL (SINGLE_SNAPSHOT, has swap data) -> FIXED with fractional daily rates."""
    rates = _swap_rates_for("OIL")
    assert rates.mode == SwapMode.FIXED
    assert rates.swap_long < 0  # long pays swap
    assert rates.swap_short > 0  # short receives swap
    assert abs(rates.swap_long - Decimal("-0.00015")) < Decimal("1e-12")  # -1.5 bps
    assert abs(rates.swap_short - Decimal("0.00003")) < Decimal("1e-12")  # +0.3 bps


def test_swap_rates_xauusd_fixed():
    """XAUUSD swap rates (working-tree calibration -0.5/+0.1 bps) -> FIXED."""
    rates = _swap_rates_for("XAUUSD")
    assert rates.mode == SwapMode.FIXED
    assert abs(rates.swap_long - Decimal("-0.00005")) < Decimal("1e-12")
    assert abs(rates.swap_short - Decimal("0.00001")) < Decimal("1e-12")


def test_swap_rates_usdcad_none():
    """USDCAD has no swap keys in calibration (Direction H pairs) -> fail closed."""
    rates = _swap_rates_for("USDCAD")
    assert rates.mode == SwapMode.NONE


def test_swap_rates_nas100_none_unusable():
    """NAS100 has swap fields but status UNVERIFIED_NO_DATA -> fail closed."""
    rates = _swap_rates_for("NAS100")
    assert rates.mode == SwapMode.NONE


def _run_round_trip(symbol: str, days_held: int, monkeypatch) -> tuple[float, float, float]:
    """Open+close a position with deterministic fills (zero slippage).

    Returns (cash_after_entry, exit_fee, realized_price_pnl) so callers can
    assert the exact swap deduction.
    """
    monkeypatch.setattr(
        "graxia.packages.quant_os.execution.adapters.paper.random.uniform",
        lambda a, b: 0.0,
    )
    adapter = PaperAdapter(initial_capital=10000.0)
    adapter.set_price(symbol, 75.0, 75.05)
    entry = adapter.submit_order(_order(symbol, "BUY", 1.0))
    if days_held > 0:
        adapter._positions[symbol]["opened_at"] = datetime.now(UTC) - timedelta(days=days_held)
    cash_after_entry = adapter._cash
    adapter.set_price(symbol, 76.0, 76.05)
    exit_res = adapter.submit_order(_order(symbol, "SELL", 1.0))
    price_pnl = (exit_res.avg_price - entry.avg_price) * 1.0  # multiplier 1.0 (non-JPY)
    return adapter, cash_after_entry, exit_res.fee, price_pnl


def test_swap_applied_on_overnight_long_close(monkeypatch):
    """Long OIL held across rollover realizes negative swap on close."""
    adapter, cash_after_entry, exit_fee, price_pnl = _run_round_trip("OIL", days_held=2, monkeypatch=monkeypatch)

    # Expected swap: 2 days incl. Wednesday triple-swap (rollover_day=3 default).
    rates = _swap_rates_for("OIL")
    policy = SwapPolicy(rates)
    entry = adapter._positions.get("OIL")  # gone after close; recompute from trade
    swap = None
    # Recompute via the public model on the same inputs the adapter used.
    # Notional = entry avg_price * quantity. Reconstruct from the fills.
    # (Adapter applied swap BEFORE removing the position; assert cash delta.)
    expected_no_swap = cash_after_entry + price_pnl - exit_fee
    assert adapter._cash < expected_no_swap, "swap must reduce cash on overnight close"
    assert "OIL" not in adapter._positions


def test_swap_exact_amount(monkeypatch):
    """Swap deduction equals SwapPolicy output on the same inputs."""
    monkeypatch.setattr(
        "graxia.packages.quant_os.execution.adapters.paper.random.uniform",
        lambda a, b: 0.0,
    )
    adapter = PaperAdapter(initial_capital=10000.0)
    adapter.set_price("OIL", 75.0, 75.05)
    entry = adapter.submit_order(_order("OIL", "BUY", 1.0))
    adapter._positions["OIL"]["opened_at"] = datetime.now(UTC) - timedelta(days=2)
    cash_after_entry = adapter._cash
    adapter.set_price("OIL", 76.0, 76.05)
    exit_res = adapter.submit_order(_order("OIL", "SELL", 1.0))
    price_pnl = (exit_res.avg_price - entry.avg_price) * 1.0

    rates = _swap_rates_for("OIL")
    notional = Decimal(str(entry.avg_price)) * Decimal("1.0")
    swap_expected = SwapPolicy(rates).apply(
        entry_time=adapter._positions.get("OIL", {}).get("opened_at") or (datetime.now(UTC) - timedelta(days=2)),
        exit_time=datetime.now(UTC),
        side="BUY",
        volume=notional,
    ).swap_applied
    # swap_expected recomputed with the same backdate used in the run:
    swap_expected = SwapPolicy(rates).apply(
        entry_time=datetime.now(UTC) - timedelta(days=2),
        exit_time=datetime.now(UTC),
        side="BUY",
        volume=notional,
    ).swap_applied

    # swap_expected is negative (long pays swap); cash was reduced by that amount.
    expected_no_swap = cash_after_entry + price_pnl - exit_res.fee
    swap_deducted = expected_no_swap - adapter._cash  # positive when swap is a cost
    assert abs(swap_deducted + float(swap_expected)) < 1e-6


def test_no_swap_same_day_close(monkeypatch):
    """Round trip within the same day: zero rollover days -> no swap."""
    adapter, cash_after_entry, exit_fee, price_pnl = _run_round_trip("OIL", days_held=0, monkeypatch=monkeypatch)
    expected = cash_after_entry + price_pnl - exit_fee
    assert abs(adapter._cash - expected) < 1e-6


def test_no_swap_for_symbol_without_rates(monkeypatch):
    """USDCAD (no measured swap keys) closes with zero swap — fail closed."""
    monkeypatch.setattr(
        "graxia.packages.quant_os.execution.adapters.paper.random.uniform",
        lambda a, b: 0.0,
    )
    adapter = PaperAdapter(initial_capital=10000.0)
    adapter.set_price("USDCAD", 1.3550, 1.35505)
    entry = adapter.submit_order(_order("USDCAD", "BUY", 100000.0))
    adapter._positions["USDCAD"]["opened_at"] = datetime.now(UTC) - timedelta(days=3)
    cash_after_entry = adapter._cash
    adapter.set_price("USDCAD", 1.3560, 1.35605)
    exit_res = adapter.submit_order(_order("USDCAD", "SELL", 100000.0))
    price_pnl = (exit_res.avg_price - entry.avg_price) * 100000.0  # 100k units, multiplier 1.0
    expected = cash_after_entry + price_pnl - exit_res.fee
    assert abs(adapter._cash - expected) < 1e-6  # no swap deducted
