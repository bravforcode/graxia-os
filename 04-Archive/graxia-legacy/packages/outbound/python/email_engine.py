"""
Email Engine for outbound campaigns.
Includes integration with Resend API for live mode.
"""

import logging
import os
import resend
from typing import Optional

logger = logging.getLogger(__name__)

class EmailEngine:
    """Handles email sending and validation for outbound campaigns."""

    def __init__(self, zerobounce_api_key: Optional[str] = None, resend_api_key: Optional[str] = None):
        self.zb_key = zerobounce_api_key or os.getenv("ZEROBOUNCE_API_KEY")
        self.resend_key = resend_api_key or os.getenv("RESEND_API_KEY")
        self.live_mode = os.getenv("LIVE_MODE") == "true"
        
        if self.live_mode and self.resend_key:
            resend.api_key = self.resend_key

    async def validate_email(self, email: str) -> bool:
        """
        Validates an email address.
        """
        if not self.live_mode:
            logger.debug(f"Skipping validation for {email} (Not Live).")
            return True

        # In prod: integration with ZeroBounce or similar
        if "invalid" in email.lower():
            return False
        return True

    async def send_email(self, to_address: str, subject: str, body: str) -> bool:
        """
        Sends an email. Uses Resend API if LIVE_MODE is true.
        """
        is_valid = await self.validate_email(to_address)
        if not is_valid:
            logger.error(f"Cannot send email. Validation failed for {to_address}.")
            return False

        if self.live_mode:
            return await self._send_live_email(to_address, subject, body)
        else:
            return await self._send_stub_email(to_address, subject, body)

    async def _send_live_email(self, to_address: str, subject: str, body: str) -> bool:
        """
        Sends a real email via Resend.
        """
        logger.info(f"📧 LIVE EMAIL SEND: To {to_address} via Resend")
        try:
            params = {
                "from": "Graxia OS <onboarding@resend.dev>",
                "to": [to_address],
                "subject": subject,
                "html": body,
            }
            resend.Emails.send(params)
            logger.info("Live email sent successfully via Resend.")
            return True
        except Exception as e:
            logger.error(f"Failed to send live email via Resend: {e}")
            return False

    async def _send_stub_email(self, to_address: str, subject: str, body: str) -> bool:
        """
        Logs email sending without actually sending anything.
        """
        logger.info(f"STUB EMAIL SEND: To {to_address}")
        print(f"[STUB] Email to: {to_address}, Subject: {subject}")
        return True
