"""
Resend API Client Factory
Creates and configures Resend client for email delivery
"""
import os
from typing import Optional
import structlog

logger = structlog.get_logger()


class ResendClient:
    """
    Resend API client wrapper.
    Provides async email sending functionality.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Resend client.
        
        Args:
            api_key: Resend API key (defaults to RESEND_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("RESEND_API_KEY")
        
        if not self.api_key:
            logger.warning("resend_client: no API key provided, email sending will fail")
        
        self.emails = self.Emails(self.api_key)
    
    class Emails:
        """Email sending interface."""
        
        def __init__(self, api_key: str):
            self.api_key = api_key
        
        async def send(self, data: dict) -> dict:
            """
            Send an email via Resend API.
            
            Args:
                data: Email data dict with keys:
                    - from: Sender email
                    - to: List of recipient emails
                    - subject: Email subject
                    - html: HTML body
                    - text: Plain text body (optional)
                    - reply_to: Reply-to email (optional)
            
            Returns:
                dict: Response with 'id' and 'status'
            
            Raises:
                Exception: If API call fails
            """
            if not self.api_key:
                raise ValueError("Resend API key not configured")
            
            # Import resend library
            try:
                import resend
            except ImportError:
                logger.error("resend library not installed, install with: pip install resend")
                raise ImportError("resend library not installed")
            
            # Configure API key
            resend.api_key = self.api_key
            
            try:
                # Send email
                response = resend.Emails.send(data)
                
                logger.info(
                    "resend_email_sent",
                    to=data.get("to"),
                    subject=data.get("subject"),
                    resend_id=response.get("id"),
                )
                
                return {
                    "id": response.get("id"),
                    "status": "sent",
                }
                
            except Exception as e:
                logger.error(
                    "resend_email_failed",
                    error=str(e),
                    to=data.get("to"),
                    subject=data.get("subject"),
                )
                raise


def create_resend_client(api_key: Optional[str] = None) -> ResendClient:
    """
    Create a Resend client instance.
    
    Args:
        api_key: Optional API key (defaults to RESEND_API_KEY env var)
    
    Returns:
        ResendClient: Configured Resend client
    """
    return ResendClient(api_key=api_key)
