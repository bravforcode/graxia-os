import stripe
import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings

class StripeSettings(BaseSettings):
    LIVE_MODE: bool = False
    STRIPE_SECRET_KEY: str = "sk_test_placeholder"
    STRIPE_WEBHOOK_SECRET: str = "whsec_test_placeholder"
    STRIPE_LIVE_SECRET_KEY: Optional[str] = None
    STRIPE_LIVE_WEBHOOK_SECRET: Optional[str] = None
    
    class Config:
        env_file = ".env"

settings = StripeSettings()

# Initialize Stripe API Key
if settings.LIVE_MODE and settings.STRIPE_LIVE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_LIVE_SECRET_KEY
else:
    stripe.api_key = settings.STRIPE_SECRET_KEY

def verify_webhook_signature(payload: str, sig_header: str) -> Optional[Dict[str, Any]]:
    """
    Verifies the signature of a Stripe webhook event.
    Returns the event object if valid, None otherwise.
    """
    webhook_secret = (
        settings.STRIPE_LIVE_WEBHOOK_SECRET 
        if settings.LIVE_MODE and settings.STRIPE_LIVE_WEBHOOK_SECRET 
        else settings.STRIPE_WEBHOOK_SECRET
    )
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event
    except ValueError as e:
        # Invalid payload
        return None
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return None
    except Exception as e:
        # Other errors
        return None

def create_checkout_session(customer_id: str, success_url: str, cancel_url: str, price_id: str):
    """
    Helper to create a Stripe Checkout Session for onboarding or credit purchase.
    """
    return stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=['card'],
        line_items=[{
            'price': price_id,
            'quantity': 1,
        }],
        mode='payment',
        success_url=success_url,
        cancel_url=cancel_url,
    )
