"""Process pending refunds against payment providers."""
from __future__ import annotations

from ...db import get_db_session
from ...services.refund_executor import RefundExecutor


async def process_refunds_with_db(db):
    return await RefundExecutor.process_pending_refunds(db)


def process_refunds():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await process_refunds_with_db(db)

    return asyncio.run(_impl())
