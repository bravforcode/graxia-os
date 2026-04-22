import logging
import asyncio
from pathlib import Path
from sqlalchemy import select, delete

from app.agents.base import BaseAgent
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeItem
from app.core.chunker import VaultChunker
from app.core.embedder import embed_batch_async
from app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class VaultIndexerAgent(BaseAgent):
    name = "vault_indexer"

    def __init__(self):
        super().__init__()
        self.chunker = VaultChunker()

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
        
        async with AsyncSessionLocal() as db:
            for file_path in md_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")
                    continue

                source_path = str(file_path.relative_to(vault_dir))
                chunks = self.chunker.process_file(content)
                
                existing_hashes_result = await db.execute(
                    select(KnowledgeItem.chunk_hash).where(KnowledgeItem.source_path == source_path)
                )
                existing_hashes = {row[0] for row in existing_hashes_result.fetchall()}

                new_chunks = [c for c in chunks if c.hash not in existing_hashes]
                
                if new_chunks:
                    current_hashes = {c.hash for c in chunks}
                    obsolete_hashes = existing_hashes - current_hashes
                    if obsolete_hashes:
                        await db.execute(
                            delete(KnowledgeItem).where(
                                KnowledgeItem.source_path == source_path,
                                KnowledgeItem.chunk_hash.in_(obsolete_hashes)
                            )
                        )

                    batch_size = 10
                    for i in range(0, len(new_chunks), batch_size):
                        batch = new_chunks[i:i+batch_size]
                        embeddings = await embed_batch_async([c.text for c in batch])
                        
                        items = []
                        for idx, c in enumerate(batch):
                            emb = embeddings[idx] if embeddings else None
                            if emb is None:
                                continue
                            
                            category = c.metadata.get("category", "vault_note")
                            
                            item = KnowledgeItem(
                                title=file_path.stem,
                                content=c.text,
                                category=category,
                                chunk_hash=c.hash,
                                chunk_index=i+idx,
                                source_path=source_path,
                                embedding=emb,
                                tags=c.metadata.get("tags", []),
                            )
                            if "project_id" in c.metadata:
                                item.tags = item.tags + [f"project:{c.metadata['project_id']}"]
                            items.append(item)
                            
                        if items:
                            db.add_all(items)
                    
                    await db.commit()

            await event_bus.emit("vault.indexed", {"vault_path": vault_path})

vault_indexer_agent = VaultIndexerAgent()
