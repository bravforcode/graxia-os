"""
Multi-agent framework for Quant OS (C1)

Deterministic rule-based agents that communicate via EventBus.
No LLM or external API calls — pure rule-based decisions.

Exception: CentaurTelegramAgent uses httpx (async HTTP) to notify
the human operator, but does NOT make trading decisions.
"""

from .analyst import TechnicalAnalystAgent
from .base import Agent
from .centaur_telegram import CentaurTelegramAgent, format_centaur_message
from .portfolio_manager import PortfolioManagerAgent
from .researcher import BullBearResearcherAgent
from .risk_auditor import RiskAuditorAgent

__all__ = [
    "Agent",
    "TechnicalAnalystAgent",
    "BullBearResearcherAgent",
    "RiskAuditorAgent",
    "PortfolioManagerAgent",
    "CentaurTelegramAgent",
    "format_centaur_message",
]
