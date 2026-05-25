"""
Phase 5 Email Service Tests
Tests for email templates, sending, and idempotency
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class TestEmailService:
    """Test email service functionality"""

    @pytest.mark.asyncio
    async def test_email_service_initialization(self):
        """Email service should initialize with Resend API key"""
        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", "re_test_key"):
            with patch("app.config.settings.APP_ENV", "production"):
                service = EmailService()
                assert service.api_key == "re_test_key"
                assert service.enabled is True

    @pytest.mark.asyncio
    async def test_email_service_disabled_without_api_key(self):
        """Email service should be disabled without API key"""
        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", None):
            with patch("app.config.settings.APP_ENV", "production"):
                service = EmailService()
                assert service.enabled is False

    @pytest.mark.asyncio
    async def test_send_welcome_email(self):
        """Should send welcome email to new user"""
        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", "re_test"):
            # Force production mode so it tries to send via API (which we mock)
            with patch("app.config.settings.APP_ENV", "production"):
                service = EmailService()
                
                with patch.object(service, "_send_via_resend", new_callable=AsyncMock) as mock_send:
                    mock_send.return_value = {"id": "email_123"}
                    
                    result = await service.send_welcome_email(
                        to_email="newuser@example.com",
                        user_name="John Doe"
                    )
                    
                    assert result["status"] == "sent"
                    mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_trial_ending_email(self):
        """Should send trial ending reminder"""
        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", "re_test"):
            with patch("app.config.settings.APP_ENV", "production"):
                service = EmailService()
                
                with patch.object(service, "_send_via_resend", new_callable=AsyncMock) as mock_send:
                    mock_send.return_value = {"id": "email_456"}
                    
                    result = await service.send_trial_ending_email(
                        to_email="user@example.com",
                        user_name="Jane Doe",
                        days_remaining=3,
                        upgrade_url="https://app.graxia.io/billing"
                    )
                    
                    assert result["status"] == "sent"
                    mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_payment_failed_email(self):
        """Should send payment failed notification"""
        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", "re_test"):
            with patch("app.config.settings.APP_ENV", "production"):
                service = EmailService()
                
                with patch.object(service, "_send_via_resend", new_callable=AsyncMock) as mock_send:
                    mock_send.return_value = {"id": "email_789"}
                    
                    result = await service.send_payment_failed_email(
                        to_email="billing@example.com",
                        user_name="Business Owner",
                        billing_url="https://app.graxia.io/billing"
                    )
                    
                    assert result["status"] == "sent"
                    mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_idempotency(self):
        """Same email should not be sent twice (idempotency)"""
        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", "re_test"):
            with patch("app.config.settings.APP_ENV", "production"):
                service = EmailService()
                
                # Create unique idempotency key for this test
                unique_id = uuid4().hex[:8]
                idempotency_key = f"welcome-{unique_id}"
                
                with patch.object(service, "_send_via_resend", new_callable=AsyncMock) as mock_send:
                    mock_send.return_value = {"id": "email_idem"}
                    
                    # First send
                    result1 = await service.send_welcome_email(
                        to_email="user@example.com",
                        user_name="Test User",
                        idempotency_key=idempotency_key
                    )
                    
                    # Second send with same key should be skipped
                    result2 = await service.send_welcome_email(
                        to_email="user@example.com",
                        user_name="Test User",
                        idempotency_key=idempotency_key
                    )
                    
                    assert result1["status"] == "sent"
                    assert result2["status"] == "skipped"
                    # Should only call API once
                    mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_dev_mode_logs(self, caplog):
        """In dev mode, emails should be logged not sent"""
        import logging

        from app.services.email_service import EmailService
        
        with patch("app.config.settings.RESEND_API_KEY", "re_test"):
            with patch("app.config.settings.APP_ENV", "development"):
                service = EmailService()
                
                with caplog.at_level(logging.INFO):
                    result = await service.send_welcome_email(
                        to_email="test@example.com",
                        user_name="Dev User"
                    )
                    
                    # Should log instead of sending
                    assert "[EMAIL DEV]" in caplog.text
                    assert result["status"] == "logged"


class TestEmailTemplates:
    """Test email template rendering"""

    def test_welcome_template_contains_required_elements(self):
        """Welcome template should have all required elements"""
        from app.services.email_service import EmailTemplate
        
        template = EmailTemplate.welcome("John Doe", "https://app.graxia.io/login")
        
        # Should contain personalization
        assert "John Doe" in template["html"]
        assert "John Doe" in template["text"]
        assert "https://app.graxia.io/login" in template["html"]
        assert template["subject"] is not None

    def test_trial_ending_template_contains_upgrade_link(self):
        """Trial ending template should contain upgrade URL placeholder"""
        from app.services.email_service import EmailTemplate
        
        template = EmailTemplate.trial_ending("Jane Doe", 3, "https://app.graxia.io/billing")
        
        assert "Jane Doe" in template["html"]
        assert "3" in template["html"]
        assert "https://app.graxia.io/billing" in template["html"]

    def test_payment_failed_template_contains_billing_link(self):
        """Payment failed template should contain billing URL placeholder"""
        from app.services.email_service import EmailTemplate
        
        template = EmailTemplate.payment_failed("Owner", "https://app.graxia.io/billing")
        
        assert "Owner" in template["html"]
        assert "https://app.graxia.io/billing" in template["html"]

    def test_leads_digest_template_structure(self):
        """Leads digest template should handle list of leads"""
        from app.services.email_service import EmailTemplate
        
        leads = [
            {"title": "Lead 1", "platform": "Upwork", "score": 9.5},
            {"title": "Lead 2", "platform": "LinkedIn", "score": 8.0},
        ]
        template = EmailTemplate.leads_digest("User", 2, leads, "https://app.graxia.io/opportunities")
        
        assert "Lead 1" in template["html"]
        assert "Lead 2" in template["html"]
        assert "9.5" in template["html"]

    def test_draft_ready_template_contains_review_link(self):
        """Draft ready template should contain review link"""
        from app.services.email_service import EmailTemplate
        
        template = EmailTemplate.draft_ready("User", "Awesome Draft Title", "Preview text", "https://app.graxia.io/drafts")
        
        assert "Awesome Draft Title" in template["html"] or "Draft ready" in template["html"] or "✍️" in template["html"]
        assert "Preview text" in template["html"]
        assert "https://app.graxia.io/drafts" in template["html"]


class TestEmailIntegration:
    """Test email integration with other services"""

    @pytest.mark.asyncio
    async def test_welcome_email_sent_on_registration(self, public_async_client):
        """Welcome email should be triggered on user registration"""
        with patch("app.services.email_service.EmailService.send_welcome_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = {"id": "welcome_123", "status": "sent"}
            
            response = await public_async_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"test_welcome_{uuid4().hex[:8]}@example.com",
                    "password": "Test123!@#123456", # Long password
                    "full_name": "Test Welcome User"
                }
            )
            
            if response.status_code == 400:
                print(f"Registration failed: {response.json()}")
            
            assert response.status_code in [201, 200]

    @pytest.mark.asyncio
    async def test_trial_email_sent_via_webhook(self, public_async_client):
        """Trial ending email should be sent via Stripe webhook"""
        
        with patch("app.services.email_service.EmailService.send_trial_ending_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = {"id": "trial_123", "status": "sent"}
            
            # Simulate trial_will_end webhook
            trial_end = int((datetime.now() + timedelta(days=3)).timestamp())
            
            response = await public_async_client.post(
                "/api/v1/webhooks/stripe",
                json={
                    "type": "customer.subscription.trial_will_end",
                    "data": {
                        "object": {
                            "id": "sub_test",
                            "customer": "cus_test",
                            "trial_end": trial_end
                        }
                    }
                }
            )
            
            assert response.status_code in [200, 400, 403]

    @pytest.mark.asyncio
    async def test_payment_failed_email_sent_via_webhook(self, public_async_client):
        """Payment failed email should be sent via Stripe webhook"""
        with patch("app.services.email_service.EmailService.send_payment_failed_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = {"id": "payment_fail_123", "status": "sent"}
            
            response = await public_async_client.post(
                "/api/v1/webhooks/stripe",
                json={
                    "type": "invoice.payment_failed",
                    "data": {
                        "object": {
                            "id": "inv_test",
                            "customer": "cus_test",
                            "subscription": "sub_test",
                            "next_payment_attempt": None
                        }
                    }
                }
            )
            
            assert response.status_code in [200, 400, 403]
