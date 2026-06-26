"""
Multi-agent framework for Quant OS (C1)

Deterministic rule-based agents that communicate via EventBus.
No LLM or external API calls — pure rule-based decisions.
"""

from .analyst import TechnicalAnalystAgent
from .base import Agent
from .portfolio_manager import PortfolioManagerAgent
from .researcher import BullBearResearcherAgent
from .risk_auditor import RiskAuditorAgent

__all__ = [
    "Agent",
    "TechnicalAnalystAgent",
    "BullBearResearcherAgent",
    "RiskAuditorAgent",
    "PortfolioManagerAgent",
]
