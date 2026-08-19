"""Billing router (P2-10) — customer-facing subscription endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.services.billing_service import BillingService

router = APIRouter()


class SubscriptionCreateRequest(BaseModel):
    customer_email: EmailStr
    plan: str = Field(..., pattern="^(standard|enterprise)$")


class SubscriptionResponse(BaseModel):
    id: str
    customer_email: str
    plan: str
    status: str
    price_cents: int
    currency: str


@router.post(
    "/subscription",
    response_model=SubscriptionResponse,
    status_code=201,
    summary="Create SaaS subscription",
)
async def create_subscription(
    payload: SubscriptionCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    try:
        sub = await BillingService.create_subscription(
            db, payload.customer_email, payload.plan
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SubscriptionResponse(
        id=str(sub.id),
        customer_email=sub.customer_email,
        plan=sub.plan,
        status=sub.status,
        price_cents=sub.price_cents,
        currency=sub.currency,
    )


class PortalSessionRequest(BaseModel):
    customer_email: EmailStr


class PortalSessionResponse(BaseModel):
    url: str


@router.post(
    "/portal-session",
    response_model=PortalSessionResponse,
    summary="Create Stripe billing portal session",
)
async def create_portal_session(
    payload: PortalSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> PortalSessionResponse:
    try:
        url = await BillingService.create_portal_session(db, payload.customer_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PortalSessionResponse(url=url)