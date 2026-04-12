from .opportunities import router as opportunities_router
from .admin import router as admin_router
from .contacts import router as contacts_router
from .drafts import router as drafts_router
from .metrics import router as metrics_router
from .cognitive import router as cognitive_router
from .system import router as system_router
from .jobs import router as jobs_router
from .email_threads import router as email_threads_router
from .tasks import router as tasks_router
from .costs import router as costs_router
from .auth import router as auth_router
from .events import router as events_router
from .scrapers import router as scrapers_router

__all__ = [
    "admin_router", "opportunities_router", "contacts_router",
    "drafts_router", "metrics_router", "cognitive_router", "system_router",
    "jobs_router", "email_threads_router", "tasks_router", "costs_router", "auth_router",
    "events_router", "scrapers_router",
]
