from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import configured_public_funnel_organization_id, settings
from app.middleware.auth import get_current_user_from_token
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.models.user import User
from app.schemas.referral import (
    ReferralAnalyticsRow,
    ReferralIssueRequest,
    ReferralIssueResponse,
)
from app.services.referral_service import (
    REFERRAL_SESSION_COOKIE,
    ReferralEligibilityError,
    ReferralError,
    ReferralNotFoundError,
    ReferralService,
)

router = APIRouter()


@router.get("/public/referrals/{code}", include_in_schema=True)
async def resolve_public_referral(
    code: str,
    request: Request,
    session_id: Annotated[str | None, Query(max_length=255)] = None,
    identity_key: Annotated[str | None, Query(max_length=255)] = None,
    referral_session_header: Annotated[str | None, Header(alias="X-Referral-Session")] = None,
    referral_identity_header: Annotated[str | None, Header(alias="X-Referral-Identity")] = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    public_organization_id = configured_public_funnel_organization_id()
    if public_organization_id is None and not settings.TESTING:
        raise HTTPException(status_code=503, detail="Public funnel is not configured")
    effective_session = (
        session_id
        or referral_session_header
        or request.cookies.get(REFERRAL_SESSION_COOKIE)
        or secrets.token_urlsafe(18)
    )
    effective_identity = identity_key or referral_identity_header
    try:
        resolution = await ReferralService(db).resolve_code(
            code=code,
            session_id=effective_session,
            organization_id=public_organization_id,
            identity_key=effective_identity,
        )
    except (ReferralNotFoundError, ReferralEligibilityError, ReferralError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found") from exc

    response = RedirectResponse(url=resolution.redirect_path, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        REFERRAL_SESSION_COOKIE,
        effective_session,
        max_age=60 * 60 * 24 * 90,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post(
    "/funnel/referrals/issue",
    response_model=ReferralIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_referral(
    payload: ReferralIssueRequest,
    org: Organization = Depends(get_org),
    current_user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> ReferralIssueResponse:
    try:
        issued = await ReferralService(db).issue_code(
            organization_id=org.id,
            issuer_user_id=current_user.id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            redirect_path=payload.redirect_path,
            owner_identity=str(current_user.id),
            bonus_asset_path=payload.bonus_asset_path,
        )
    except ReferralError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ReferralIssueResponse(
        code=issued.code,
        referral_url=f"/r/{issued.code}",
        source_type=issued.record.source_type,
        audience=issued.record.audience,
        redirect_path=issued.record.redirect_path,
        bonus_asset_path=issued.record.bonus_asset_path,
        commission_rate=issued.record.commission_rate,
        hold_days=issued.record.hold_days,
    )


@router.get(
    "/funnel/analytics/referrals",
    response_model=list[ReferralAnalyticsRow],
)
async def referral_analytics(
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
) -> list[ReferralAnalyticsRow]:
    return await ReferralService(db).analytics(org.id)
