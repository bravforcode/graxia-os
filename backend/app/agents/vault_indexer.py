import logging
from pathlib import Path

from app.agents.base import BaseAgent
from app.config import settings
from app.core.event_bus import event_bus
from app.database import AsyncSessionLocal
from app.services.knowledge_service import get_knowledge_service

logger = logging.getLogger(__name__)


class VaultIndexerAgent(BaseAgent):
    name = "vault_indexer"

    async def index_vault(self):
        vault_path = getattr(settings, "OBSIDIAN_VAULT_PATH", None)
        if not vault_path:
            logger.warning("No OBSIDIAN_VAULT_PATH configured")
            return

        vault_dir = Path(vault_path)
        if not vault_dir.exists():
            logger.warning(f"Vault path {vault_path} does not exist")
            return

        md_files = list(vault_dir.rglob("*.md"))
        total_indexed = 0

        async with AsyncSessionLocal() as db:
            service = await get_knowledge_service()
            for file_path in md_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")
                    continue

                source_path = str(file_path.relative_to(vault_dir))
                indexed = await service.index_markdown_content(
                    db=db, title=file_path.stem, content=content, source_path=source_path
                )
                total_indexed += indexed

            await db.commit()

        logger.info(f"Vault indexing complete. Total indexed chunks: {total_indexed}")
        await event_bus.emit("vault.indexed", {"vault_path": vault_path, "count": total_indexed})


vault_indexer_agent = VaultIndexerAgent()
