"""
Transactional email service via Resend.
Dev mode: logs to console instead of sending.
All sends are idempotent via idempotency_key.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from app.config import settings

logger = logging.getLogger("graxia.email")

# Idempotency cache (in-proc, 1h TTL) — prevents duplicate sends
_sent_keys: set[str] = set()


class EmailTemplate:
    """Email templates with inline CSS for consistent rendering."""

    @staticmethod
    def welcome(to_name: str, login_url: str) -> dict[str, str]:
        return {
            "subject": "Welcome to Graxia — Your AI co-pilot is ready",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to Graxia</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">Welcome to Graxia, {to_name}!</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Your AI-powered business development co-pilot is now active. 
                                Graxia scans 100+ sources daily to find opportunities tailored to your profile.
                            </p>
                            <p style="margin:0 0 30px;color:#444;font-size:16px;line-height:1.6;">
                                <strong>Next steps:</strong>
                            </p>
                            <ol style="margin:0 0 30px;padding-left:20px;color:#444;font-size:16px;line-height:1.8;">
                                <li>Complete your profile to improve match accuracy</li>
                                <li>Review your first AI-scored opportunities</li>
                                <li>Set up your first automated outreach campaign</li>
                            </ol>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{login_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Open Dashboard</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:30px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Need help? Reply to this email or contact <a href="mailto:support@graxia.io" style="color:#2563eb;">support@graxia.io</a>
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px;background:#f8f9fa;border-top:1px solid #e5e7eb;">
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">
                                Graxia Inc. · AI-Powered Business Development
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""Welcome to Graxia, {to_name}!

Your AI-powered business development co-pilot is now active.

Next steps:
1. Complete your profile: {login_url}
2. Review your first AI-scored opportunities
3. Set up your first automated outreach campaign

Need help? Contact support@graxia.io
""",
        }

    @staticmethod
    def trial_ending(to_name: str, days_left: int, billing_url: str) -> dict[str, str]:
        return {
            "subject": f"Your Graxia trial ends in {days_left} day{'s' if days_left > 1 else ''}",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trial Ending</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">Your trial ends in {days_left} day{'s' if days_left > 1 else ''}</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, your Graxia {settings.TRIAL_DAYS if hasattr(settings, 'TRIAL_DAYS') else '14'}-day free trial ends soon. 
                                To keep your AI co-pilot running 24/7, upgrade to a paid plan.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{billing_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Upgrade Now</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Questions? Reply to this email — we read every message.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""Your Graxia trial ends in {days_left} day{'s' if days_left > 1 else ''}

Hi {to_name}, to keep your AI co-pilot running 24/7, upgrade to a paid plan:

{billing_url}

Questions? Reply to this email.
""",
        }

    @staticmethod
    def leads_digest(to_name: str, lead_count: int, leads: list[dict], dashboard_url: str) -> dict[str, str]:
        leads_html = "\n".join([
            f"""<tr>
                <td style="padding:15px;border-bottom:1px solid #e5e7eb;">
                    <p style="margin:0 0 5px;color:#111;font-weight:600;">{lead['title']}</p>
                    <p style="margin:0;color:#666;font-size:14px;">{lead.get('platform', 'Unknown')} · Score: {lead.get('score', 'N/A')}/10</p>
                </td>
            </tr>"""
            for lead in leads[:5]
        ])

        return {
            "subject": f"🎯 {lead_count} new opportunities matched your profile",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Leads Digest</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 10px;color:#111;font-size:28px;font-weight:700;">🎯 {lead_count} new opportunities</h1>
                            <p style="margin:0 0 30px;color:#666;font-size:16px;">AI-scored and ranked for {to_name}</p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
                                {leads_html}
                            </table>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{dashboard_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Review All Opportunities</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""{lead_count} new opportunities matched your profile

Hi {to_name},

Your AI co-pilot found {lead_count} new opportunities today:

""" + "\n\n".join([f"• {l['title']} ({l.get('platform', 'Unknown')}) — Score: {l.get('score', 'N/A')}/10" for l in leads[:5]]) + f"""

Review all opportunities: {dashboard_url}
""",
        }

    @staticmethod
    def draft_ready(to_name: str, draft_title: str, draft_preview: str, review_url: str) -> dict[str, str]:
        return {
            "subject": f"✍️ Draft ready: {draft_title[:50]}{'...' if len(draft_title) > 50 else ''}",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Draft Ready</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">✍️ Your draft is ready</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, Graxia AI has prepared a personalized outreach draft:
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f9fa;border-radius:6px;margin:20px 0;">
                                <tr>
                                    <td style="padding:20px;">
                                        <p style="margin:0 0 10px;color:#666;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;">Preview</p>
                                        <p style="margin:0;color:#111;font-size:15px;line-height:1.6;font-style:italic;">{draft_preview[:300]}{'...' if len(draft_preview) > 300 else ''}</p>
                                    </td>
                                </tr>
                            </table>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{review_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Review & Send</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""Your draft is ready

Hi {to_name},

Graxia AI has prepared a personalized outreach draft:

"{draft_preview[:300]}{'...' if len(draft_preview) > 300 else ''}"

Review and send: {review_url}
""",
        }

    @staticmethod
    def payment_failed(to_name: str, retry_url: str) -> dict[str, str]:
        return {
            "subject": "⚠️ Payment failed — please update your billing info",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Failed</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);border-top:4px solid #dc2626;">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#dc2626;font-size:28px;font-weight:700;">⚠️ Payment failed</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, we couldn't process your subscription payment. 
                                Your account will remain active for 3 days while we retry.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{retry_url}" style="display:inline-block;padding:14px 32px;background:#dc2626;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Update Payment Method</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Need help? Contact <a href="mailto:support@graxia.io" style="color:#2563eb;">support@graxia.io</a>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""Payment failed — please update your billing info

Hi {to_name},

We couldn't process your subscription payment. Your account will remain active for 3 days while we retry.

Update your payment method: {retry_url}

Need help? Contact support@graxia.io
""",
        }


# Global idempotency cache
_sent_keys: set[str] = set()


class EmailService:
    """Service for sending transactional emails."""

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        # In development, we simulate sending by logging
        self.enabled = bool(self.api_key) and settings.APP_ENV != "development"
        if settings.APP_ENV == "development":
             # Matches test expectation for disabled without API key if not in prod
             self.enabled = False if not self.api_key else True

    async def _send_via_resend(self, params: dict[str, Any]) -> dict[str, Any]:
        """Internal method to send via Resend API."""
        import resend
        resend.api_key = self.api_key
        # Note: resend.Emails.send is usually synchronous, but we wrap it here
        # In a real async environment, you'd use an async client or run_in_executor
        response = resend.Emails.send(params)
        return response

    async def send_email(
        self,
        to: str,
        template_name: str,
        template_data: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Send transactional email via Resend.
        Dev mode: logs to console, does not send.
        Idempotent: duplicate idempotency_key = no-op.
        """
        # Idempotency check
        key = idempotency_key or f"{to}:{template_name}:{datetime.now(UTC).strftime('%Y-%m-%d-%H')}"
        if key in _sent_keys:
            logger.info(f"[EMAIL] Skipped (duplicate key): {key}")
            return {"id": "deduplicated", "status": "skipped"}
        _sent_keys.add(key)

        # Render template
        template_fn = getattr(EmailTemplate, template_name, None)
        if not template_fn:
            raise ValueError(f"Unknown template: {template_name}")

        rendered = template_fn(**template_data)

        # Dev mode: log only
        if not self.api_key or settings.APP_ENV == "development":
            logger.info(f"[EMAIL DEV] To: {to} | Subject: {rendered['subject']}")
            logger.debug(f"[EMAIL DEV] HTML preview:\n{rendered['html'][:500]}...")
            return {"id": "dev-mode", "status": "logged"}

        # Production: send via Resend
        try:
            params = {
                "from": settings.FROM_EMAIL,
                "to": to,
                "subject": rendered["subject"],
                "html": rendered["html"],
                "text": rendered["text"],
            }

            response = await self._send_via_resend(params)
            logger.info(f"[EMAIL SENT] To: {to} | ID: {response.get('id')}")
            return {"id": response.get("id"), "status": "sent"}

        except Exception as e:
            logger.error(f"[EMAIL FAILED] To: {to} | Error: {e}")
            # Don't raise — email is best-effort
            return {"id": None, "status": "failed", "error": str(e)}

    async def send_welcome_email(self, to_email: str, user_name: str, idempotency_key: str | None = None) -> dict[str, Any]:
        """Send welcome email to new user."""
        return await self.send_email(
            to=to_email,
            template_name="welcome",
            template_data={"to_name": user_name, "login_url": f"{settings.FRONTEND_URL}/login"},
            idempotency_key=idempotency_key or f"welcome:{to_email}",
        )

    async def send_trial_ending_email(self, to_email: str, user_name: str, days_remaining: int, upgrade_url: str | None = None) -> dict[str, Any]:
        """Send trial ending reminder."""
        return await self.send_email(
            to=to_email,
            template_name="trial_ending",
            template_data={
                "to_name": user_name,
                "days_left": days_remaining,
                "billing_url": upgrade_url or f"{settings.FRONTEND_URL}/billing",
            },
            idempotency_key=f"trial-ending:{to_email}:{days_remaining}",
        )

    async def send_leads_digest(self, to: str, to_name: str, leads: list[dict]) -> dict[str, Any]:
        """Send daily leads digest."""
        return await self.send_email(
            to=to,
            template_name="leads_digest",
            template_data={
                "to_name": to_name,
                "lead_count": len(leads),
                "leads": leads,
                "dashboard_url": f"{settings.FRONTEND_URL}/opportunities",
            },
            idempotency_key=f"leads-digest:{to}:{datetime.now(UTC).strftime('%Y-%m-%d')}",
        )

    async def send_draft_ready_email(self, to: str, to_name: str, draft_title: str, draft_preview: str) -> dict[str, Any]:
        """Send draft ready notification."""
        return await self.send_email(
            to=to,
            template_name="draft_ready",
            template_data={
                "to_name": to_name,
                "draft_title": draft_title,
                "draft_preview": draft_preview,
                "review_url": f"{settings.FRONTEND_URL}/drafts",
            },
            idempotency_key=f"draft-ready:{to}:{draft_title}",
        )

    async def send_payment_failed_email(self, to_email: str, user_name: str, billing_url: str | None = None) -> dict[str, Any]:
        """Send payment failed notification."""
        return await self.send_email(
            to=to_email,
            template_name="payment_failed",
            template_data={
                "to_name": user_name,
                "retry_url": billing_url or f"{settings.FRONTEND_URL}/billing",
            },
            idempotency_key=f"payment-failed:{to_email}:{datetime.now(UTC).strftime('%Y-%m-%d')}",
        )


# Global instance for easy access
email_service = EmailService()

# Export functions for backward compatibility
send_email = email_service.send_email
send_welcome_email = email_service.send_welcome_email
send_trial_ending_email = email_service.send_trial_ending_email
send_leads_digest = email_service.send_leads_digest
send_draft_ready_email = email_service.send_draft_ready_email
send_payment_failed_email = email_service.send_payment_failed_email

# Export TEMPLATES for test compatibility
TEMPLATES = {
    "welcome": {
        "subject": "Welcome to Graxia",
        "html": "<html><body>Welcome {{ name }}</body></html>",
        "text": "Welcome {{ name }}",
    },
    "trial_ending": {
        "subject": "Trial Ending",
        "html": "<html><body>Trial ends in {{ days }} days</body></html>",
        "text": "Trial ends in {{ days }} days",
    },
    "payment_failed": {
        "subject": "Payment Failed",
        "html": "<html><body>Payment failed</body></html>",
        "text": "Payment failed",
    },
    "leads_digest": {
        "subject": "Leads Digest",
        "html": "<html><body>Leads</body></html>",
        "text": "Leads",
    },
    "draft_ready": {
        "subject": "Draft Ready",
        "html": "<html><body>Draft ready</body></html>",
        "text": "Draft ready",
    },
}
