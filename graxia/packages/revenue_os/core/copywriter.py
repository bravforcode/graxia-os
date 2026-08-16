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

    def __init__(self, client, model: str = "claude-sonnet-4.6"):
        """
        Initialize copywriter.

        Args:
            client: Anthropic API client
            model: Claude model to use
        """
        self.client = client
        self.model = model

    async def generate_sales_email(
        self,
        lead_data: Dict[str, Any],
        product_data: Optional[Dict[str, Any]] = None,
        tone: str = "professional",
    ) -> Dict[str, Any]:
        """
        Generate personalized sales email for a lead.

        Args:
            lead_data: Lead information (name, email, company, pain_point)
            product_data: Optional product information (name, value_prop, price)
            tone: Writing tone (professional, casual, urgent)

        Returns:
            dict: {"html", "text", "tokens_used": {"input", "output", "total"}}
        """
        lead_name = lead_data.get("name") or lead_data.get("email", "").split("@")[0]

        product_info = ""
        if product_data:
            product_info = f"""
Product: {product_data.get('name')}
Value Proposition: {product_data.get('value_prop', '')}
Price: {product_data.get('price', '')}
"""

        prompt = f"""You are a professional sales copywriter. Write a personalized sales email.

Lead Information:
- Name: {lead_name}
- Email: {lead_data.get('email')}
- Company: {lead_data.get('company', 'unknown')}
- Pain Point: {lead_data.get('pain_point', '')}

{product_info}
Tone: {tone}

Requirements:
1. Subject line: Compelling, under 60 characters
2. Email body: {tone} tone
3. Clear value proposition
4. Single clear call-to-action
5. Length: 150-250 words
6. Format: HTML and plain text versions

Write the email now."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            result = {
                "html": f"<html><body>{content.replace(chr(10), '<br>')}</body></html>",
                "text": content,
                "tokens_used": {
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": input_tokens + output_tokens,
                },
            }

            logger.info(
                "sales_email_generated",
                lead_email=lead_data.get("email"),
                tone=tone,
                tokens=result["tokens_used"]["total"],
            )

            return result

        except Exception as e:
            logger.error(
                "sales_email_generation_failed",
                error=str(e),
                lead_email=lead_data.get("email"),
            )
            raise

    async def generate_proposal(
        self,
        client_data: Dict[str, Any],
        service_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate service proposal for a client.

        Args:
            client_data: Client information (name, company, industry)
            service_data: Service offering details (name, scope, timeline, price)

        Returns:
            dict: {"html", "text", "tokens_used": {"input", "output", "total"}}
        """
        client_name = client_data.get("name") or client_data.get("email", "").split("@")[0]

        prompt = f"""You are a professional proposal writer. Create a service proposal.

Client:
- Name: {client_name}
- Company: {client_data.get('company', '')}
- Industry: {client_data.get('industry', '')}

Service Offer:
- Name: {service_data.get('name')}
- Scope: {service_data.get('scope', '')}
- Timeline: {service_data.get('timeline', '')}
- Price: {service_data.get('price', '')}

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
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            result = {
                "html": f"<html><body>{content.replace(chr(10), '<br>')}</body></html>",
                "text": content,
                "tokens_used": {
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": input_tokens + output_tokens,
                },
            }

            logger.info(
                "proposal_generated",
                client_email=client_data.get("email"),
                service=service_data.get("name"),
                tokens=result["tokens_used"]["total"],
            )

            return result

        except Exception as e:
            logger.error(
                "proposal_generation_failed",
                error=str(e),
                client_email=client_data.get("email"),
            )
            raise


async def generate_sales_email(
    lead: Dict[str, Any],
    campaign: Dict[str, Any],
    model: str,
    anthropic_client,
) -> Dict[str, Any]:
    """
    Convenience function for generating sales emails.

    Args:
        lead: Lead information
        campaign: Campaign details
        model: Claude model to use
        anthropic_client: Anthropic API client

    Returns:
        dict: Generated email content
    """
    copywriter = Copywriter(client=anthropic_client, model=model)
    return await copywriter.generate_sales_email(lead_data=lead, product_data=campaign)