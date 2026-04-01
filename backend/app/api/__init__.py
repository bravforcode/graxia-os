from .opportunities import router as opportunities_router
from .contacts import router as contacts_router
from .submissions import router as submissions_router
from .drafts import router as drafts_router
from .metrics import router as metrics_router
from .cognitive import router as cognitive_router
from .system import router as system_router

__all__ = [
    "opportunities_router", "contacts_router", "submissions_router",
    "drafts_router", "metrics_router", "cognitive_router", "system_router",
]
