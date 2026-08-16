"""Multi-currency treasury — ledger balances per currency + THB equivalents."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.marketplace_sync import _fx_rates
from ..models import LedgerEntry


async def treasury_summary(db: AsyncSession) -> dict:
    """Net ledger position per currency; THB equivalents via stored fx rates
    (foreign units per 1 THB, from the fx channel row). Currencies without a
    rate are reported in missing_rates, not silently converted."""
    rows = (await db.execute(
        select(LedgerEntry.currency, func.sum(LedgerEntry.amount_cents))
        .group_by(LedgerEntry.currency))).all()
    fx = await _fx_rates(db)
    thb_rates = fx.get("THB") or {}
    balances = []
    missing = []
    total_thb = 0
    for currency, cents in rows:
        cents = int(cents or 0)
        if currency == "THB" or currency in thb_rates:
            thb_eq = cents if currency == "THB" else int(cents / thb_rates[currency])
            total_thb += thb_eq
        else:
            thb_eq = None
            missing.append(currency)
        balances.append({"currency": currency, "cents": cents,
                         "thb_equivalent_cents": thb_eq})
    return {"balances": balances, "total_thb_cents": total_thb,
            "missing_rates": missing}
