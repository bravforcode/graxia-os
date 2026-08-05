"""Order repository — PostgreSQL-backed order persistence.

Replaces JSONL ledger as primary store. JSONL kept as audit trail.

Usage:
    from execution.order_repository import OrderRepository
    repo = OrderRepository(session)
    order_id = await repo.create({"symbol": "XAUUSD", "side": "BUY", "volume": 0.01})
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class OrderRepository:
    """CRUD operations on quant_orders table."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, order_data: dict) -> str:
        """Insert order, return order_id."""
        order_id = str(uuid.uuid4())
        await self._session.execute(
            text(
                """INSERT INTO quant_orders
                   (id, symbol, side, volume, price, status, order_type, created_at)
                   VALUES (:id, :symbol, :side, :volume, :price, :status, :order_type, :created_at)"""
            ),
            {
                "id": order_id,
                "symbol": order_data["symbol"],
                "side": order_data["side"],
                "volume": order_data["volume"],
                "price": order_data.get("price"),
                "status": "PENDING",
                "order_type": order_data.get("order_type", "MARKET"),
                "created_at": datetime.now(timezone.utc),
            },
        )
        await self._session.commit()
        return order_id

    async def update_status(self, order_id: str, status: str, **kwargs: object) -> bool:
        """Update order status and optional fields."""
        sets = ["status = :status"]
        params: dict = {"status": status, "id": order_id}

        if "filled_price" in kwargs:
            sets.append("filled_price = :filled_price")
            params["filled_price"] = kwargs["filled_price"]
        if "filled_volume" in kwargs:
            sets.append("filled_volume = :filled_volume")
            params["filled_volume"] = kwargs["filled_volume"]
        if "broker_order_id" in kwargs:
            sets.append("broker_order_id = :broker_order_id")
            params["broker_order_id"] = kwargs["broker_order_id"]
        if "rejection_reason" in kwargs:
            sets.append("rejection_reason = :rejection_reason")
            params["rejection_reason"] = kwargs["rejection_reason"]

        set_clause = ", ".join(sets)
        result = await self._session.execute(
            text(f"UPDATE quant_orders SET {set_clause} WHERE id = :id"),
            params,
        )
        await self._session.commit()
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def get_by_id(self, order_id: str) -> Optional[dict]:
        """Get order by ID."""
        result = await self._session.execute(
            text("SELECT * FROM quant_orders WHERE id = :id"),
            {"id": order_id},
        )
        row = result.first()
        return dict(row._mapping) if row else None

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """Get all open orders, optionally filtered by symbol."""
        query = "SELECT * FROM quant_orders WHERE status NOT IN ('FILLED', 'CANCELLED', 'REJECTED')"
        params: dict = {}
        if symbol:
            query += " AND symbol = :symbol"
            params["symbol"] = symbol
        query += " ORDER BY created_at DESC"
        result = await self._session.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_by_signal_id(self, signal_id: str) -> Optional[dict]:
        """Get order by signal ID (idempotency check)."""
        result = await self._session.execute(
            text("SELECT * FROM quant_orders WHERE signal_id = :sid"),
            {"sid": signal_id},
        )
        row = result.first()
        return dict(row._mapping) if row else None

    async def count_today(self) -> int:
        """Count orders created today."""
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM quant_orders WHERE created_at >= CURRENT_DATE")
        )
        return result.scalar() or 0
