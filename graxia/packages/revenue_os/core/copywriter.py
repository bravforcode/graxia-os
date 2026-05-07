"""
Revenue OS AI Copywriter
Generate sales emails, proposals, and content using Claude
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class CopywritingResult:
    """Result from AI copywriting generation"""
    subject: str
    html_body: str
    text_body: str
    prompt_tokens: int
    completion_tokens: int
    model_used: str


class Copywriter:
    """
    AI-powered copywriter using Anthropic Claude.
    Generates personalized sales emails and proposals.
    """
    
    def __init__(self, anthropic_client, model: str = "claude-sonnet-4-6"):
        """
        Initialize copywriter.
        
        Args:
            anthropic_client: Anthropic API client
            model: Claude model to use
        """
        self.client = anthropic_client
        self.model = model
    
    async def generate_sales_email(
        self,
        lead: Dict[str, Any],
        campaign: Dict[str, Any],
        product: Optional[Dict[str, Any]] = None,
    ) -> CopywritingResult:
        """
        Generate personalized sales email for a lead.
        
        Args:
            lead: Lead information (email, name, score, etc.)
            campaign: Campaign details (name, objective, offer_angle)
            product: Optional product information
        
        Returns:
            CopywritingResult: Generated email content
        """
        # Build context
        lead_name = lead.get("name") or lead.get("email", "").split("@")[0]
        campaign_name = campaign.get("name", "")
        offer_angle = campaign.get("offer_angle", "")
        
        product_info = ""
        if product:
            product_info = f"""
Product: {product.get('name')}
Promise: {product.get('promise', '')}
Price: {product.get('price_cents', 0) / 100:.2f} THB
"""
        
        # Construct prompt
        prompt = f"""You are a professional sales copywriter. Write a personalized sales email.

Lead Information:
- Name: {lead_name}
- Email: {lead.get('email')}
- Source: {lead.get('source', 'unknown')}
- Score: {lead.get('score', 0)}/100

Campaign:
- Name: {campaign_name}
- Objective: {campaign.get('objective', 'lead_to_sale')}
- Offer Angle: {offer_angle}

{product_info}

Requirements:
1. Subject line: Compelling, under 60 characters
2. Email body: Professional, conversational tone
3. Clear value proposition
4. Single clear call-to-action
5. Length: 150-250 words
6. Format: HTML and plain text versions

Write the email now."""

        try:
            # Call Claude API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            content = response.content[0].text
            
            # Parse response (simple split for now)
            lines = content.split("\n")
            subject = ""
            html_body = ""
            
            # Extract subject
            for line in lines:
                if line.lower().startswith("subject:"):
                    subject = line.split(":", 1)[1].strip()
                    break
            
            # Use full content as body if no clear structure
            html_body = content.replace(f"Subject: {subject}\n", "").strip()
            text_body = html_body  # Simple version for now
            
            # Wrap in HTML
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    {html_body.replace(chr(10), '<br>')}
</body>
</html>
"""
            
            result = CopywritingResult(
                subject=subject or f"Regarding {campaign_name}",
                html_body=html_body,
                text_body=text_body,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=self.model,
            )
            
            logger.info(
                "sales_email_generated",
                lead_email=lead.get("email"),
                campaign=campaign_name,
                subject=result.subject,
                tokens=result.prompt_tokens + result.completion_tokens,
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "sales_email_generation_failed",
                error=str(e),
                lead_email=lead.get("email"),
            )
            raise
    
    async def generate_proposal(
        self,
        lead: Dict[str, Any],
        service_offer: Dict[str, Any],
    ) -> CopywritingResult:
        """
        Generate service proposal for a lead.
        
        Args:
            lead: Lead information
            service_offer: Service offering details
        
        Returns:
            CopywritingResult: Generated proposal
        """
        lead_name = lead.get("name") or lead.get("email", "").split("@")[0]
        
        prompt = f"""You are a professional proposal writer. Create a service proposal.

Client:
- Name: {lead_name}
- Email: {lead.get('email')}

Service Offer:
- Name: {service_offer.get('name')}
- Promise: {service_offer.get('promise', '')}
- Deliverables: {service_offer.get('deliverables', '')}
- Price Range: {service_offer.get('price_min_cents', 0) / 100:.2f} - {service_offer.get('price_max_cents', 0) / 100:.2f} THB

Requirements:
1. Subject: Professional proposal title
2. Structure: Executive Summary, Scope, Deliverables, Timeline, Investment
3. Tone: Professional but approachable
4. Length: 400-600 words
5. Clear next steps

Write the proposal now."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            content = response.content[0].text
            
            # Parse subject
            lines = content.split("\n")
            subject = ""
            for line in lines:
                if line.lower().startswith("subject:") or line.lower().startswith("title:"):
                    subject = line.split(":", 1)[1].strip()
                    break
            
            html_body = content.replace(f"Subject: {subject}\n", "").strip()
            text_body = html_body
            
            # Wrap in HTML
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 40px;">
    {html_body.replace(chr(10), '<br>')}
</body>
</html>
"""
            
            result = CopywritingResult(
                subject=subject or f"Proposal: {service_offer.get('name')}",
                html_body=html_body,
                text_body=text_body,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=self.model,
            )
            
            logger.info(
                "proposal_generated",
                lead_email=lead.get("email"),
                service=service_offer.get("name"),
                tokens=result.prompt_tokens + result.completion_tokens,
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "proposal_generation_failed",
                error=str(e),
                lead_email=lead.get("email"),
            )
            raise


async def generate_sales_email(
    lead: Dict[str, Any],
    campaign: Dict[str, Any],
    model: str,
    anthropic_client,
) -> CopywritingResult:
    """
    Convenience function for generating sales emails.
    
    Args:
        lead: Lead information
        campaign: Campaign details
        model: Claude model to use
        anthropic_client: Anthropic API client
    
    Returns:
        CopywritingResult: Generated email
    """
    copywriter = Copywriter(anthropic_client, model)
    return await copywriter.generate_sales_email(lead, campaign)
