import pytest
import sys
import os

# Add relevant paths to sys.path for importing local packages
sys.path.append(os.path.abspath("C:/Users/menum/graxia/packages/bravos_core/python"))
sys.path.append(os.path.abspath("C:/Users/menum/graxia/packages/logging/python"))

from privacy import scrub_pii
from model_router import router
from tracing import get_tracer

def test_privacy_scrubber_e2e():
    """Validates that PII is correctly scrubbed from a multi-line document."""
    sensitive_doc = """
    User Request from: john.doe@example.com
    Contact number: +1-555-555-0199
    Payment details: 4111 2222 3333 4444 (VISA)
    Message: Please call me ASAP.
    """
    
    scrubbed = scrub_pii(sensitive_doc)
    
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_CC]" in scrubbed
    assert "john.doe@example.com" not in scrubbed
    assert "4111 2222 3333 4444" not in scrubbed

def test_model_router_success():
    """Tests that the router uses the primary model under normal conditions."""
    prompt = "Hello World"
    result = router.route_request(prompt)
    
    assert result["status"] == "success"
    assert result["provider"] == "primary"
    assert "Primary Model Response" in result["response"]

def test_model_router_fallback():
    """Tests that the router falls back to the secondary model on primary failure."""
    prompt = "Fail me now" # Triggers simulated failure in PrimaryModelAPI
    result = router.route_request(prompt)
    
    assert result["status"] == "fallback"
    assert result["provider"] == "fallback"
    assert "Fallback Model (Ollama) Response" in result["response"]
    assert "Primary API Connection Timeout" in result["error"]

def test_otel_tracing_registration():
    """Verifies that the tracer is correctly initialized and registered."""
    tracer = get_tracer()
    assert tracer is not None
    
    with tracer.start_as_current_span("e2e_validation_span"):
        # Simulate work
        pass

def test_webhook_processing_simulated():
    """Simulates a Go-Live payment webhook event processing with hardening."""
    payment_event = {
        "event_type": "payment.succeeded",
        "user_email": "customer@secure.com",
        "amount": 100.0,
        "raw_payload": "CC: 1234-5678-9012-3456"
    }
    
    # 1. Privacy Scrubbing
    scrubbed_payload = scrub_pii(payment_event["raw_payload"])
    assert "[REDACTED_CC]" in scrubbed_payload
    
    # 2. Model Routing for Analysis
    analysis_prompt = f"Analyze payment success for {payment_event['user_email']}"
    result = router.route_request(analysis_prompt)
    assert result["status"] == "success"
    
    # 3. Tracing
    tracer = get_tracer()
    with tracer.start_as_current_span("webhook_process"):
        # Simulate database update
        pass

if __name__ == "__main__":
    pytest.main([__file__])
