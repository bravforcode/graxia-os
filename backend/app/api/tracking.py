from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.core.tracking import verify_token
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/t", tags=["tracking"])

_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00"
    b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)


def _safe_url(target: str) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return target


@router.get("/open.gif")
async def open_pixel(request: Request, token: str) -> Response:
    payload = verify_token(token) or {}
    if settings.EMAIL_TRACKING_ENABLED:
        await log_audit_event(
            app=request.app,
            action="outreach.open",
            event_type="tracking",
            event_category="outreach",
            severity="INFO",
            outcome="success",
            metadata={
                "token": token[:16],
                "payload": payload,
                "ua": request.headers.get("user-agent", ""),
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            request_path=str(request.url.path),
            request_method=request.method,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent"),
            entity_type="contact",
            entity_id=str(payload.get("contact_id") or ""),
        )
    return Response(content=_PIXEL, media_type="image/gif")


@router.get("/click")
async def click_redirect(request: Request, token: str) -> Response:
    payload = verify_token(token) or {}
    target = _safe_url(str(payload.get("target_url") or ""))
    if settings.EMAIL_TRACKING_ENABLED:
        await log_audit_event(
            app=request.app,
            action="outreach.click",
            event_type="tracking",
            event_category="outreach",
            severity="INFO",
            outcome="success",
            metadata={
                "token": token[:16],
                "payload": payload,
                "ua": request.headers.get("user-agent", ""),
            },
            request_path=str(request.url.path),
            request_method=request.method,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent"),
            entity_type="contact",
            entity_id=str(payload.get("contact_id") or ""),
        )
    return RedirectResponse(url=target or (settings.FRONTEND_URL or "/"), status_code=302)

