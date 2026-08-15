"""Ads platform abstraction — one client per network (Meta first)."""
from __future__ import annotations

import abc
from typing import Optional


class AdPlatformError(Exception):
    """Raised when an ad platform call fails."""


class AdPlatformClient(abc.ABC):
    """Contract every ad network client implements. All methods async."""

    @abc.abstractmethod
    async def list_campaigns(self) -> list[dict]:
        """Return [{platform_campaign_id, name, status, daily_budget_cents}]."""

    @abc.abstractmethod
    async def get_metrics(self, campaign_ids: list[str]) -> dict[str, dict]:
        """Return {campaign_id: {spend_cents, revenue_cents, roas}}."""

    @abc.abstractmethod
    async def set_budget(self, campaign_id: str, daily_budget_cents: int) -> None:
        """Set campaign daily budget (cents)."""

    @abc.abstractmethod
    async def set_status(self, campaign_id: str, active: bool) -> None:
        """Pause/activate a campaign."""
