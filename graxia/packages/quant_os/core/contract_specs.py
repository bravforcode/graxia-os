"""Canonical per-symbol contract specs — single source of truth.

Prior to 2026-07-28, backtest/engine.py's InlineContractSpec and
risk/position_sizer.py's _SYMBOL_CONTRACT_SIZES were two independently
maintained tables that disagreed and both silently dropped several
symbols (XAGUSD, NAS100, US30, BTCUSD, USOIL) to a gold-shaped default.
That defect caused a false-positive backtest edge (F27) and inflated
the catastrophic NAS100/US30 legs in Trial #2001 by 2-3 orders of
magnitude. Both modules now read from this table instead of keeping
their own copy.

For USD-quoted linear instruments, tick_value = trade_contract_size *
trade_tick_size (no currency conversion needed, unlike e.g. USDJPY).

Entries marked ASSUMPTION are industry-standard placeholders, not
broker-verified — none of the affected symbols currently have real
cost-calibration data (see config/tradeable_universe.json) or are
in the tradeable/paper universe, so this only affects backtest/research
fidelity, not live capital, as of this writing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple


class ContractSpec(NamedTuple):
    contract_size: Decimal
    tick_size: Decimal
    tick_value: Decimal
    verified: bool  # False = industry-standard assumption, not broker-measured


_FX = Decimal("100000")
_CRYPTO_UNIT = Decimal("1")

CONTRACT_SPECS: dict[str, ContractSpec] = {
    # Explicit synthetic spec for backtests / paper sims. contract_size=1 keeps
    # units==lots (self-consistent P&L). NOT a silent default: real unmapped
    # symbols still raise in InlineContractSpec.for_symbol (F27 protection intact).
    "BACKTEST": ContractSpec(Decimal("1"), Decimal("0.01"), Decimal("0.01"), False),
    "XAUUSD": ContractSpec(Decimal("100"), Decimal("0.01"), Decimal("1.0"), True),
    "XAGUSD": ContractSpec(Decimal("5000"), Decimal("0.001"), Decimal("5.0"), False),
    "EURUSD": ContractSpec(_FX, Decimal("0.0001"), Decimal("10.0"), True),
    "GBPUSD": ContractSpec(_FX, Decimal("0.0001"), Decimal("10.0"), True),
    "USDJPY": ContractSpec(_FX, Decimal("0.01"), Decimal("6.67"), True),
    "AUDUSD": ContractSpec(_FX, Decimal("0.0001"), Decimal("10.0"), True),
    "USDCAD": ContractSpec(_FX, Decimal("0.0001"), Decimal("7.50"), True),
    "USDCHF": ContractSpec(_FX, Decimal("0.0001"), Decimal("11.00"), True),
    "NZDUSD": ContractSpec(_FX, Decimal("0.0001"), Decimal("10.0"), True),
    "BTCUSDT": ContractSpec(_CRYPTO_UNIT, Decimal("0.01"), Decimal("0.01"), True),
    "BTCUSD": ContractSpec(_CRYPTO_UNIT, Decimal("0.01"), Decimal("0.01"), False),
    "ETHUSD": ContractSpec(_CRYPTO_UNIT, Decimal("0.01"), Decimal("0.01"), False),
    "NAS100": ContractSpec(Decimal("1"), Decimal("0.01"), Decimal("0.01"), False),
    "US30": ContractSpec(Decimal("1"), Decimal("0.01"), Decimal("0.01"), False),
    "USOIL": ContractSpec(Decimal("1000"), Decimal("0.01"), Decimal("10.0"), False),
    "OIL": ContractSpec(Decimal("1000"), Decimal("0.01"), Decimal("10.0"), False),
}


def get_spec(symbol: str) -> ContractSpec | None:
    """Return the canonical spec for symbol, or None if unmapped (caller must decide fallback)."""
    return CONTRACT_SPECS.get(symbol.upper())


def risk_based_units(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
) -> float:
    """Raw underlying units for a fixed-fractional risk budget.

    SINGLE SOURCE OF TRUTH for upstream sizers
    (core/agents/portfolio_manager.py, risk/engine.py::_layer4). Returns units of
    underlying (e.g. troy oz for XAUUSD), NOT broker lots — execution/adapters/mt5.py
    is the only place that converts units -> lots via get_spec(symbol).contract_size.

    Keeping the conversion in one boundary adapter prevents the 2-source-of-truth
    drift that caused F27 (InlineContractSpec vs _SYMBOL_CONTRACT_SIZES disagreeing).
    """
    if not entry_price or not stop_loss:
        return 0.0
    risk_per_unit = abs(float(entry_price) - float(stop_loss))
    if risk_per_unit <= 0:
        return 0.0
    risk_budget = float(equity) * float(risk_pct)
    return risk_budget / risk_per_unit
