from fastapi import FastAPI, HTTPException, Request, Header, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import sys
import os

# Ensure shared packages are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from packages.billing.python.stripe_client import verify_webhook_signature
from packages.logging.python.audit import audit_service

app = FastAPI(title="BravOS Revenue API", version="1.0.0")

class EntitlementResponse(BaseModel):
    tenant_id: str
    feature_key: str
    status: str
    limits: Dict[str, Any]

class MeteringRequest(BaseModel):
    tenant_id: str
    metric_key: str
    value: float
    reference_id: Optional[str] = None

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "revenue-api"}

@app.post("/v1/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Receives events directly from Stripe.
    MUST verify signature before processing.
    """
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    payload = await request.body()
    
    event = verify_webhook_signature(payload, stripe_signature)
    if not event:
        # Log the failed attempt for security auditing
        await audit_service.log_event(
            actor_id="stripe_webhook",
            actor_type="EXTERNAL_SERVICE",
            event_type="WEBHOOK_VERIFICATION_FAILED",
            resource_id="stripe",
            resource_type="WEBHOOK",
            action="VERIFY",
            status="FAILURE"
        )
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    event_type = event.get('type')
    event_data = event.get('data', {}).get('object', {})

    # 1. Idempotency Check & Storage (Simulated here, requires DB in prod)
    # check_if_processed(event['id'])
    # store_raw_webhook(event['id'], event_type, payload)

    # 2. Process specific events
    if event_type == 'payment_intent.succeeded':
        # Simulated Revenue Ledger update
        print(f"Credit tenant account for payment {event.get('id')}")
        # Simulated Entitlements update
        print(f"Activate requested feature for payment {event.get('id')}")
    elif event_type == 'invoice.payment_failed':
        # Simulated Revenue Ledger update
        print(f"Record failed attempt for invoice {event.get('id')}")
        # Simulated Entitlements update
        print(f"Suspend specific features if necessary for invoice {event.get('id')}")

    # Log successful processing
    await audit_service.log_event(
        actor_id="stripe_webhook",
        actor_type="EXTERNAL_SERVICE",
        event_type=f"STRIPE_EVENT_{event_type.upper()}",
        resource_id=event.get('id'),
        resource_type="WEBHOOK_EVENT",
        action="PROCESS",
        status="SUCCESS"
    )

    return {"status": "success"}

@app.get("/v1/entitlements/{tenant_id}", response_model=EntitlementResponse)
async def check_entitlement(tenant_id: str, feature_key: str):
    """
    Called by Agent Mesh or other services to verify access before executing tasks.
    """
    # Simulated DB check
    # if not has_active_entitlement(tenant_id, feature_key):
    #     raise HTTPException(status_code=403, detail="Payment required or entitlement expired")
    
    return EntitlementResponse(
        tenant_id=tenant_id,
        feature_key=feature_key,
        status="active",
        limits={"max_tokens_per_day": 100000}
    )

@app.post("/v1/metering/report")
async def report_usage(req: MeteringRequest):
    """
    Called by services to report usage (e.g., LLM tokens).
    Pushes to Redis for atomic increments.
    """
    # 1. Push to Redis (Simulated)
    # redis_client.incrbyfloat(f"usage:{req.tenant_id}:{req.metric_key}", req.value)
    
    return {"status": "recorded", "metric": req.metric_key, "value_added": req.value}
