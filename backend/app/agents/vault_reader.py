import logging
import uuid
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.core.domain_events import VaultSynced

logger = logging.getLogger(__name__)


class VaultReaderAgent(BaseAgent):
    """Agent that reads frontmatter changes from vault and syncs to database."""

    name = "vault_reader"

    async def sync_vault_changes(self, vault_path: str | None = None) -> dict[str, Any]:
        """Scan vault for opportunity status changes and sync to database.

        Args:
            vault_path: Path to vault root. If None, uses configured path.

        Returns:
            Dict with sync statistics (synced_count, failed_count, etc.)
        """
        from app.integrations.obsidian import scan_changed_opportunity_files
        from app.database import AsyncSessionLocal
        from app.models.opportunity import Opportunity
        from sqlalchemy import select

        if vault_path is None:
            from app.config import settings
            vault_path = getattr(settings, "OBSIDIAN_VAULT_PATH", None)

        if not vault_path:
            logger.warning("vault_reader: no vault path configured")
            return {"synced_count": 0, "failed_count": 0, "error": "vault_path not configured"}

        vault_path_obj = Path(vault_path)
        changed_files = scan_changed_opportunity_files(vault_path_obj)

        if not changed_files:
            return {"synced_count": 0, "failed_count": 0}

        synced_count = 0
        failed_count = 0

        async with AsyncSessionLocal() as db:
            for file_info in changed_files:
                try:
                    # Extract OPP ID from filename (OPP-123.md)
                    file_path: Path = file_info["file_path"]
                    filename = file_path.stem  # Remove .md extension

                    # Extract the UUID portion from OPP-<uuid>
                    if not filename.startswith("OPP-"):
                        continue

                    try:
                        opp_id_str = filename[4:]  # Remove "OPP-" prefix
                        opp_id = uuid.UUID(opp_id_str)
                    except (ValueError, IndexError):
                        logger.warning(f"vault_reader: invalid opportunity filename: {filename}")
                        failed_count += 1
                        continue

                    # Get opportunity from database
                    stmt = select(Opportunity).where(Opportunity.id == opp_id)
                    result = await db.execute(stmt)
                    opp = result.scalar_one_or_none()

                    if not opp:
                        logger.warning(f"vault_reader: opportunity not found: {opp_id}")
                        failed_count += 1
                        continue

                    # Get new status from vault frontmatter
                    new_status = file_info.get("status")
                    if not new_status:
                        logger.debug(f"vault_reader: no status in vault for {filename}")
                        failed_count += 1
                        continue

                    # Update opportunity status if changed
                    old_status = opp.status
                    if old_status != new_status:
                        # Validate status against constraint
                        valid_statuses = {
                            "found",
                            "scored",
                            "decided",
                            "reviewed",
                            "approved",
                            "in_progress",
                            "applied",
                            "waiting",
                            "accepted",
                            "rejected",
                            "withdrawn",
                            "ignored",
                        }
                        if new_status not in valid_statuses:
                            logger.warning(
                                f"vault_reader: invalid status for {filename}: {new_status}"
                            )
                            failed_count += 1
                            continue

                        opp.status = new_status
                        await db.commit()
                        logger.info(
                            f"vault_reader: synced opportunity status",
                            opportunity_id=str(opp_id),
                            old_status=old_status,
                            new_status=new_status,
                        )

                        # Emit domain event
                        event = VaultSynced(
                            opportunity_id=str(opp_id),
                            old_status=old_status,
                            new_status=new_status,
                            aggregate_id=str(opp_id),
                            aggregate_type="opportunity",
                        )
                        await self.bus.emit_domain_event(event)

                        synced_count += 1
                    else:
                        logger.debug(
                            f"vault_reader: no status change for {filename}",
                            status=new_status,
                        )
                        synced_count += 1

                except Exception as e:
                    logger.error(
                        f"vault_reader: failed to sync opportunity",
                        filename=file_info.get("file_path"),
                        error=str(e),
                        exc_info=True,
                    )
                    failed_count += 1

        await self.log_audit(
            action="vault_sync",
            details={
                "vault_path": str(vault_path),
                "synced_count": synced_count,
                "failed_count": failed_count,
            },
            success=failed_count == 0,
        )

        return {"synced_count": synced_count, "failed_count": failed_count}
