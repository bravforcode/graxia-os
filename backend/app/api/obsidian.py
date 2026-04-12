"""
Obsidian API endpoints.
"""
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from structlog import get_logger

from app.agents.obsidian_sync import obsidian_sync_agent
from app.config import settings
from app.integrations.obsidian import get_obsidian

logger = get_logger(__name__)

router = APIRouter(tags=["obsidian"])


class ObsidianHealthResponse(BaseModel):
    configured: bool
    vault_path: str | None
    api_url: str | None
    root_folder: str | None
    auto_bootstrap: bool
    auto_sync_enabled: bool


class SyncRequest(BaseModel):
    entity_type: Literal["opportunity", "submission", "contact", "task", "knowledge_item"]
    entity_id: str


class SyncResponse(BaseModel):
    success: bool
    message: str
    path: str | None = None


class BootstrapResponse(BaseModel):
    success: bool = True
    root_folder: str
    project_count: int
    skill_count: int
    knowledge_count: int = 0
    synced_entities: dict[str, int] = Field(default_factory=dict)


class ContextCaptureRequest(BaseModel):
    project_key: str
    title: str
    summary: str
    details: str
    tags: list[str] = Field(default_factory=list)
    source_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/obsidian/health")
async def obsidian_health() -> ObsidianHealthResponse:
    try:
        obsidian = await get_obsidian()
        return ObsidianHealthResponse(
            configured=True,
            vault_path=str(obsidian.vault_path) if obsidian.vault_path else None,
            api_url=obsidian.api_url,
            root_folder=obsidian.root_folder or None,
            auto_bootstrap=settings.OBSIDIAN_AUTO_BOOTSTRAP,
            auto_sync_enabled=settings.OBSIDIAN_AUTO_SYNC_ENABLED,
        )
    except ValueError:
        return ObsidianHealthResponse(
            configured=False,
            vault_path=None,
            api_url=None,
            root_folder=getattr(settings, "OBSIDIAN_ROOT_FOLDER", "Second Brain"),
            auto_bootstrap=settings.OBSIDIAN_AUTO_BOOTSTRAP,
            auto_sync_enabled=settings.OBSIDIAN_AUTO_SYNC_ENABLED,
        )


@router.post("/obsidian/sync", response_model=SyncResponse)
async def sync_to_obsidian(request: SyncRequest) -> SyncResponse:
    try:
        if request.entity_type == "opportunity":
            await obsidian_sync_agent.sync_opportunity(request.entity_id)
        elif request.entity_type == "submission":
            await obsidian_sync_agent.sync_submission(request.entity_id)
        elif request.entity_type == "contact":
            await obsidian_sync_agent.sync_contact(request.entity_id)
        elif request.entity_type == "task":
            await obsidian_sync_agent.sync_task(request.entity_id)
        elif request.entity_type == "knowledge_item":
            await obsidian_sync_agent.sync_knowledge_item(request.entity_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown entity type: {request.entity_type}")

        return SyncResponse(
            success=True,
            message=f"Synced {request.entity_type} {request.entity_id} to Obsidian",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("obsidian_sync_failed", error=str(exc), request=request.model_dump())
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/obsidian/bootstrap", response_model=BootstrapResponse)
async def bootstrap_obsidian_second_brain() -> BootstrapResponse:
    try:
        result = await obsidian_sync_agent.bootstrap_second_brain()
        return BootstrapResponse(**result)
    except Exception as exc:
        logger.error("obsidian_bootstrap_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/obsidian/context", response_model=SyncResponse)
async def capture_context(request: ContextCaptureRequest) -> SyncResponse:
    try:
        path = await obsidian_sync_agent.capture_context(
            project_key=request.project_key,
            title=request.title,
            summary=request.summary,
            details=request.details,
            tags=request.tags,
            source_url=request.source_url,
            metadata=request.metadata,
        )
        return SyncResponse(
            success=True,
            message=f"Captured context for {request.project_key}",
            path=path,
        )
    except Exception as exc:
        logger.error("obsidian_context_capture_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/obsidian/daily-note", response_model=SyncResponse)
async def create_daily_note() -> SyncResponse:
    try:
        await obsidian_sync_agent.create_daily_note()
        return SyncResponse(success=True, message="Daily note created")
    except Exception as exc:
        logger.error("daily_note_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/obsidian/weekly-review", response_model=SyncResponse)
async def create_weekly_review() -> SyncResponse:
    try:
        await obsidian_sync_agent.create_weekly_review()
        return SyncResponse(success=True, message="Weekly review created")
    except Exception as exc:
        logger.error("weekly_review_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/obsidian/vault-stats")
async def get_vault_stats() -> dict[str, Any]:
    """Return vault file counts and tag frequencies for the dashboard."""
    try:
        from app.agents.cog_loop import extract_vault_tag_frequencies
        from pathlib import Path

        obsidian = await get_obsidian()
        vault_path = obsidian.vault_path

        if vault_path is None:
            return {
                "total_notes": 0,
                "top_tags": [],
                "vault_path": None,
                "vault_exists": False,
            }

        all_files = list(vault_path.rglob("*.md")) if vault_path.exists() else []
        tag_freqs = extract_vault_tag_frequencies(vault_path)
        top_tags = sorted(tag_freqs.items(), key=lambda x: x[1], reverse=True)[:20]

        return {
            "total_notes": len(all_files),
            "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
            "vault_path": str(vault_path),
            "vault_exists": vault_path.exists(),
        }
    except Exception as exc:
        logger.error("vault_stats_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
