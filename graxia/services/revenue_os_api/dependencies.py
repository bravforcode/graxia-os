"""
graxia/services/revenue_os_api/dependencies.py
FastAPI dependency injection — fixes CRIT-06 (fail-fast credentials).

Security decisions:
  - ADMIN_API_KEY read from env at request time (not at import time)
  - Fail-fast: RuntimeError at startup if APP_ENV=production and key missing
  - Constant-time comparison prevents timing attacks
  - Stripe HMAC validated before payload deserialization
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

import stripe
from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger(__name__)


def _get_admin_api_key() -> str:
    """Fail-fast in production if key is not set."""
    key = os.getenv("ADMIN_API_KEY")
    if not key:
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError(
                "ADMIN_API_KEY environment variable must be set in production. "
                "Set it via your secrets manager."
            )
        # Dev-only fallback — loud log so nobody misses it
        logger.warning(
            "ADMIN_API_KEY not set — using dev-only placeholder. "
            "This MUST be set before deploying to production."
        )
        return "dev-only-placeholder-never-use-in-prod"
    return key


def _get_stripe_webhook_secret() -> str:
    """Fail-fast in production if secret is not set."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("STRIPE_WEBHOOK_SECRET must be set in production")
        return "whsec_dev_placeholder"
    return secret


# ─────────────────────────────────────────────────────────────────────────────
# Admin API key auth
# ─────────────────────────────────────────────────────────────────────────────

async def require_admin_api_key(
    request: Request,
    x_admin_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> None:
    """
    Validates admin API key from either:
      - X-Admin-Api-Key header (preferred)
      - Authorization: Bearer <key> header

    Uses constant-time comparison to prevent timing attacks.
    """
    expected = _get_admin_api_key()

    provided = x_admin_api_key
    if not provided and authorization:
        if authorization.startswith("Bearer "):
            provided = authorization[len("Bearer "):]

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-Admin-Api-Key header or Authorization: Bearer <key>",
        )

    # hmac.compare_digest prevents timing-based key enumeration
    if not hmac.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Invalid API key attempt from IP: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Stripe HMAC validation
# ─────────────────────────────────────────────────────────────────────────────

async def require_stripe_hmac(request: Request) -> dict:
    """
    Validates Stripe webhook signature.
    Returns the deserialized event dict on success.
    Handles both Stripe SDK v4 (stripe.error.SignatureVerificationError)
    and v5+ (stripe.SignatureVerificationError) — fixes MED-04.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )

    secret = _get_stripe_webhook_secret()

    # Handle both Stripe SDK v4 and v5+ exception locations
    try:
        StripeSignatureError = stripe.error.SignatureVerificationError  # type: ignore[attr-defined]
    except AttributeError:
        StripeSignatureError = stripe.SignatureVerificationError  # SDK v5+

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        return dict(event)
    except StripeSignatureError as exc:
        logger.warning("Stripe signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        )
    except Exception as exc:
        logger.error("Unexpected error validating Stripe webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed webhook payload",
        )
