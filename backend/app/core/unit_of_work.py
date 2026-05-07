from app.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)

class AsyncUnitOfWork:
    def __init__(self):
        self.session_factory = AsyncSessionLocal
        self.session = None

    async def __aenter__(self):
        self.session = self.session_factory()
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        if exc_type is not None:
            await self.rollback()
            logger.error(f"UoW rollback due to: {exc_val}")
        else:
            await self.commit()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
