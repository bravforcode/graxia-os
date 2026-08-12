"""Canonical business event types for Graxia runtime."""
from __future__ import annotations

from typing import Literal

BusinessEventType = Literal[
    "product.created",
    "product.updated",
    "product.published.requested",
    "checkout.started",
    "payment.succeeded",
    "payment.failed",
    "order.created",
    "delivery.access.granted",
    "delivery.opened",
    "lead.captured",
    "recommendation.created",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
]

FUNNEL_RUNTIME_EVENT_TYPES: tuple[str, ...] = (
    "product.created",
    "product.updated",
    "product.published.requested",
    "checkout.started",
    "payment.succeeded",
    "payment.failed",
    "order.created",
    "delivery.access.granted",
    "delivery.opened",
    "lead.captured",
    "recommendation.created",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
)
