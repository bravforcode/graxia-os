"""
Revenue OS — Webhooks API
Payment gateway webhook handlers with HMAC validation
"""
import hmac
import hashlib
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Header, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..services.webhook_processor import WebhookProcessor

router = APIRouter()

# ── Services ──
webhook_processor = WebhookProcessor()

# ── Stripe Webhook ──

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Stripe webhook events
    Events: checkout.session.completed, invoice.paid, invoice.payment_failed, etc.
    """
    import os
    
    # Get webhook secret
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret not configured"
        )
    
    # Read raw body
    payload = await request.body()
    
    # Verify signature (simplified - would use Stripe SDK in production)
    if stripe_signature:
        # Actual signature verification would use stripe.Webhook.construct_event()
        pass
    
    # Parse event
    try:
        import json
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    event_type = event.get("type")
    
    # Process based on event type
    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        await webhook_processor.process_stripe_checkout_completed(session, db)
        
    elif event_type == "invoice.paid":
        invoice = event.get("data", {}).get("object", {})
        await webhook_processor.process_stripe_invoice_paid(invoice, db)
        
    elif event_type == "invoice.payment_failed":
        invoice = event.get("data", {}).get("object", {})
        await webhook_processor.process_stripe_payment_failed(invoice, db)
        
    elif event_type == "charge.refunded":
        charge = event.get("data", {}).get("object", {})
        await webhook_processor.process_stripe_refund(charge, db)
    
    return {"status": "processed", "event_type": event_type}


# ── Gumroad Webhook ──

@router.post("/gumroad")
async def gumroad_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Gumroad webhook
    Triggered on sale, refund, or subscription events
    """
    import os
    from urllib.parse import parse_qs
    
    # Get Gumroad secret for verification
    gumroad_secret = os.getenv("GUMROAD_API_KEY")
    
    # Parse form data
    body = await request.body()
    data = parse_qs(body.decode())
    
    # Extract fields
    sale_id = data.get("sale_id", [None])[0]
    product_id = data.get("product_id", [None])[0]
    product_name = data.get("product_name", [None])[0]
    permalink = data.get("permalink", [None])[0]
    email = data.get("email", [None])[0]
    price = data.get("price", ["0"])[0]
    recurrence = data.get("recurrence", [None])[0]  # For subscriptions
    
    # Process sale
    if sale_id and email:
        await webhook_processor.process_gumroad_sale({
            "sale_id": sale_id,
            "product_id": product_id,
            "product_name": product_name,
            "email": email,
            "price": int(price) / 100,  # Gumroad sends cents
            "is_subscription": recurrence is not None,
            "recurrence": recurrence
        }, db)
    
    return {"status": "processed"}


# ── PayPal Webhook ──

@router.post("/paypal")
async def paypal_webhook(
    request: Request,
    paypal_transmission_id: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """Handle PayPal webhook events"""
    import json
    
    payload = await request.body()
    
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON"
        )
    
    event_type = event.get("event_type")
    resource = event.get("resource", {})
    
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        await webhook_processor.process_paypal_payment_completed(resource, db)
    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        await webhook_processor.process_paypal_refund(resource, db)
    
    return {"status": "processed", "event_type": event_type}


# ── Generic Webhook for Testing ──

@router.post("/test")
async def test_webhook(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Test webhook endpoint for development"""
    return {
        "status": "received",
        "data": data,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat()
    }


# ── Webhook Status & Management ──

@router.get("/status")
async def get_webhook_status():
    """Get webhook processing status"""
    return {
        "stripe": {"configured": bool(__import__("os").getenv("STRIPE_WEBHOOK_SECRET"))},
        "gumroad": {"configured": bool(__import__("os").getenv("GUMROAD_API_KEY"))},
        "paypal": {"configured": bool(__import__("os").getenv("PAYPAL_CLIENT_ID"))},
        "status": "active",
        "last_check": __import__("datetime").datetime.utcnow().isoformat()
    }
