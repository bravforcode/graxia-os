"""Position repository — PostgreSQL-backed position persistence.

Usage:
    from execution.position_repository import PositionRepository
    repo = PositionRepository(session)
    await repo.upsert("XAUUSD", 0.01, 2350.50)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PositionRepository:
    """CRUD operations on quant_positions table."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(
        self,
        symbol: str,
        volume: float,
        avg_price: float,
        unrealized_pnl: float = 0,
        side: str = "BUY",
    ) -> None:
        """Insert or update position."""
        await self._session.execute(
            text(
                """INSERT INTO quant_positions
                   (symbol, volume, avg_price, unrealized_pnl, side, updated_at)
                   VALUES (:symbol, :volume, :avg_price, :pnl, :side, :updated)
                   ON CONFLICT (symbol) DO UPDATE SET
                     volume = EXCLUDED.volume,
                     avg_price = EXCLUDED.avg_price,
                     unrealized_pnl = EXCLUDED.unrealized_pnl,
                     side = EXCLUDED.side,
                     updated_at = EXCLUDED.updated_at"""
            ),
            {
                "symbol": symbol,
                "volume": volume,
                "avg_price": avg_price,
                "pnl": unrealized_pnl,
                "side": side,
                "updated": datetime.now(timezone.utc),
            },
        )
        await self._session.commit()

    async def close(self, symbol: str) -> bool:
        """Set position volume to 0."""
        result = await self._session.execute(
            text(
                """UPDATE quant_positions
                   SET volume = 0, updated_at = :now
                   WHERE symbol = :symbol"""
            ),
            {"symbol": symbol, "now": datetime.now(timezone.utc)},
        )
        await self._session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def get_all(self) -> list[dict]:
        """Get all open positions (volume != 0)."""
        result = await self._session.execute(
            text("SELECT * FROM quant_positions WHERE volume != 0")
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_by_symbol(self, symbol: str) -> Optional[dict]:
        """Get position by symbol."""
        result = await self._session.execute(
            text("SELECT * FROM quant_positions WHERE symbol = :symbol"),
            {"symbol": symbol},
        )
        row = result.first()
        return dict(row._mapping) if row else None

    async def total_exposure(self) -> float:
        """Get total absolute volume across all positions."""
        result = await self._session.execute(
            text("SELECT COALESCE(SUM(ABS(volume)), 0) FROM quant_positions WHERE volume != 0")
        )
        return float(result.scalar() or 0)

    async def update_pnl(self, symbol: str, unrealized_pnl: float) -> bool:
        """Update unrealized P&L for a position."""
        result = await self._session.execute(
            text(
                """UPDATE quant_positions
                   SET unrealized_pnl = :pnl, updated_at = :now
                   WHERE symbol = :symbol"""
            ),
            {"symbol": symbol, "pnl": unrealized_pnl, "now": datetime.now(timezone.utc)},
        )
        await self._session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]
