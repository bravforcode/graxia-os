from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.agents import router as agents_router
from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.cognitive import router as cognitive_router
from app.api.commands import router as commands_router
from app.api.contacts import router as contacts_router
from app.api.costs import router as costs_router
from app.api.drafts import router as drafts_router
from app.api.email_threads import router as email_threads_router
from app.api.events import router as events_router
from app.api.funnel_products import router as funnel_products_router
from app.api.funnel_webhooks import router as funnel_webhooks_router
from app.api.funnel_delivery import router as funnel_delivery_router
from app.api.funnel_analytics import router as funnel_analytics_router
from app.api.funnel_ai import router as funnel_ai_router
from app.api.funnel_automation import router as funnel_automation_router
from app.api.lead_magnets import router as lead_magnets_router
from app.api.inbox import router as inbox_router
from app.api.integrations import router as integrations_router
from app.api.jobs import router as jobs_router
from app.api.metrics import router as metrics_router
from app.api.obsidian import router as obsidian_router
from app.api.opportunities import router as opportunities_router
from app.api.orchestration import router as orchestration_router
from app.api.outreach import router as outreach_router
from app.api.runs import router as runs_router
from app.api.scrapers import router as scrapers_router
from app.api.skills import router as skills_router
from app.api.submissions import router as submissions_router
from app.api.system import router as system_router
from app.api.tasks import router as tasks_router
from app.api.tracking import router as tracking_router
from app.api.websockets import router as websockets_router

api_router = APIRouter()

# Authentication & Infrastructure
api_router.include_router(auth_router)
api_router.include_router(metrics_router, prefix="/api/v1")
api_router.include_router(system_router, prefix="/api/v1")

# Core Business Domains (v1)
api_router.include_router(admin_router, prefix="/api/v1")
api_router.include_router(agents_router, prefix="/api/v1")
api_router.include_router(approvals_router, prefix="/api/v1")
api_router.include_router(calendar_router, prefix="/api/v1")
api_router.include_router(commands_router, prefix="/api/v1")
api_router.include_router(opportunities_router, prefix="/api/v1")
api_router.include_router(contacts_router, prefix="/api/v1")
api_router.include_router(drafts_router, prefix="/api/v1")
api_router.include_router(cognitive_router, prefix="/api/v1")
api_router.include_router(submissions_router, prefix="/api/v1")
api_router.include_router(inbox_router, prefix="/api/v1")
api_router.include_router(integrations_router, prefix="/api/v1")
api_router.include_router(jobs_router, prefix="/api/v1")
api_router.include_router(runs_router, prefix="/api/v1")
api_router.include_router(skills_router, prefix="/api/v1")

# Specialized Routers (No prefix specified in original main.py)
api_router.include_router(funnel_products_router, prefix="/api/v1/funnel", tags=["funnel"])
api_router.include_router(funnel_delivery_router, prefix="/api/v1/funnel", tags=["funnel"])
api_router.include_router(funnel_analytics_router, prefix="/api/v1/funnel", tags=["funnel"])
api_router.include_router(funnel_ai_router, prefix="/api/v1/funnel", tags=["funnel_ai"])
api_router.include_router(lead_magnets_router, prefix="/api/v1", tags=["funnel"])
api_router.include_router(funnel_automation_router, prefix="/api/v1/funnel", tags=["funnel_automation"])
api_router.include_router(funnel_webhooks_router, prefix="/api/v1/funnel/webhooks", tags=["funnel_webhooks"])
api_router.include_router(email_threads_router)
api_router.include_router(obsidian_router)
api_router.include_router(outreach_router)
api_router.include_router(tasks_router)
api_router.include_router(costs_router)
api_router.include_router(events_router)
api_router.include_router(scrapers_router)
api_router.include_router(tracking_router)

# Advanced Orchestration
api_router.include_router(orchestration_router, prefix="/api/v1/orchestration", tags=["orchestration"])

# WebSockets
api_router.include_router(websockets_router)
