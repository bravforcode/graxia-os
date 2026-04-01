import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api import (
    opportunities_router, contacts_router, submissions_router,
    drafts_router, metrics_router, cognitive_router, system_router,
)
from app.core.event_bus import event_bus
from app.core.scheduler import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _register_event_handlers() -> None:
    """Wire up all agent event subscriptions."""
    from app.agents.scorer import scorer_agent
    from app.agents.decision_engine import decision_engine
    from app.agents.drafter import drafter_agent
    from app.agents.briefer import briefer_agent
    from app.agents.learning_engine import learning_engine
    from app.agents.playbook_capture import playbook_capture
    from app.agents.failure_analysis import failure_analysis
    from app.agents.compound_engine import compound_engine

    event_bus.subscribe("opportunity.found", scorer_agent.handle_new_opportunity)
    event_bus.subscribe("opportunity.scored", decision_engine.handle_scored_opportunity)
    event_bus.subscribe("opportunity.decided", drafter_agent.handle_decided_opportunity)
    event_bus.subscribe("opportunity.decided", briefer_agent.handle_decided_opportunity)
    event_bus.subscribe("submission.won", learning_engine.handle_win)
    event_bus.subscribe("submission.won", playbook_capture.handle_win)
    event_bus.subscribe("submission.won", compound_engine.handle_win)
    event_bus.subscribe("submission.lost", learning_engine.handle_loss)
    event_bus.subscribe("submission.lost", failure_analysis.handle_loss)
    event_bus.subscribe("submission.sent", compound_engine.handle_submission_sent)
    event_bus.subscribe("draft.approved", briefer_agent.handle_draft_approved)
    event_bus.subscribe("cognitive_state.updated", decision_engine.update_cognitive_context)
    event_bus.subscribe("cognitive_state.updated", briefer_agent.update_cognitive_context)
    event_bus.subscribe("scraper.failed", briefer_agent.handle_scraper_alert)
    event_bus.subscribe("ai.cost_limit_reached", briefer_agent.handle_cost_alert)
    logger.info("Event handlers registered")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Personal OS starting up...")

    # Run bootstrap check
    try:
        from app.core.bootstrap import check_system_ready
        is_ready, mode, issues = await check_system_ready()
        if is_ready:
            _register_event_handlers()
            asyncio.create_task(event_bus.start_processing())
            scheduler.setup()
            scheduler.start()
            logger.info(f"Startup complete. Mode: {mode}")
        else:
            logger.warning(f"System blocked — issues: {issues}")
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)

    yield

    # Shutdown
    event_bus.stop()
    scheduler.stop()
    logger.info("Personal OS shut down.")


app = FastAPI(
    title="Personal Sovereign Enterprise OS",
    description="Autonomous opportunity engine for P (Phirawit Jitnarong)",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(submissions_router, prefix="/api/v1")
app.include_router(drafts_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(cognitive_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")

# Serve dashboard static files
dashboard_path = Path("/app/dashboard") if Path("/app/dashboard").exists() else Path("dashboard")
if dashboard_path.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_path), html=True), name="dashboard")

@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "Personal OS v3"}

@app.get("/")
async def root():
    index = dashboard_path / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"service": "Personal OS v3", "docs": "/docs", "dashboard": "/dashboard"}
