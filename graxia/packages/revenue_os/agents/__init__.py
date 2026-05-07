"""
graxia/packages/revenue_os/agents/__init__.py
Agent-specific business logic for Visionary, Sales, and Chief of Staff.
"""
from .visionary import propose_campaign
from .sales import draft_outreach_email
from .chief_of_staff import escalate_issue
from .event_handlers import (
    VisionaryAgentHandler,
    SalesAgentHandler,
    ChiefOfStaffHandler,
    route_event_to_handlers,
    AGENT_HANDLERS,
)

__all__ = [
    "propose_campaign",
    "draft_outreach_email",
    "escalate_issue",
    "VisionaryAgentHandler",
    "SalesAgentHandler",
    "ChiefOfStaffHandler",
    "route_event_to_handlers",
    "AGENT_HANDLERS",
]
