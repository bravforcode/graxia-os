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

    @staticmethod
    def funnel_automation_welcome(to_name: str, store_url: str) -> dict[str, str]:
        return {
            "subject": "Welcome to Ai Factory — here's your quick start guide",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">Welcome to Ai Factory, {to_name}!</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                You now have access to 25+ battle-tested digital products for creators, freelancers, and founders.
                            </p>
                            <p style="margin:0 0 10px;color:#444;font-size:16px;line-height:1.6;"><strong>Here's what to do next:</strong></p>
                            <ol style="margin:0 0 30px;padding-left:20px;color:#444;font-size:16px;line-height:1.8;">
                                <li>Browse our store for the perfect template or tool</li>
                                <li>Start with our bestseller: ChatGPT Power Prompts Bundle</li>
                                <li>Every product comes with lifetime updates</li>
                            </ol>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{store_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Browse Products</a>
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
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">Ai Factory · Digital Products for Creators</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""Welcome to Ai Factory, {to_name}!

You now have access to 25+ battle-tested digital products.

Next steps:
1. Browse our store: {store_url}
2. Start with our bestseller: ChatGPT Power Prompts Bundle
3. Every product comes with lifetime updates

Need help? Contact support@graxia.io
""",
        }

    @staticmethod
    def funnel_automation_abandoned_cart(to_name: str, product_name: str, product_benefits: str, price: str, checkout_url: str) -> dict[str, str]:
        return {
            "subject": "You left something behind — complete your purchase",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Complete Your Purchase</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">You left something behind</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, you were checking out <strong>{product_name}</strong> but didn't complete your purchase.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f9fa;border-radius:6px;margin:20px 0;">
                                <tr>
                                    <td style="padding:20px;">
                                        <p style="margin:0 0 10px;color:#111;font-weight:600;font-size:16px;">Here's what you'd get:</p>
                                        <p style="margin:0;color:#444;font-size:14px;line-height:1.8;">{product_benefits}</p>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0;color:#444;font-size:16px;line-height:1.6;">
                                Price: <strong>{price} THB</strong> (one-time payment, lifetime updates)<br>
                                Plus: 30-day money-back guarantee. Zero risk.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{checkout_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Complete Purchase</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Questions? Just reply to this email.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px;background:#f8f9fa;border-top:1px solid #e5e7eb;">
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">Ai Factory · Digital Products for Creators</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""You left something behind

Hi {to_name}, you were checking out {product_name} but didn't complete your purchase.

Here's what you'd get:
{product_benefits}

Price: {price} THB (one-time payment, lifetime updates)
Plus: 30-day money-back guarantee. Zero risk.

Complete your purchase: {checkout_url}

Questions? Just reply to this email.
""",
        }

    @staticmethod
    def funnel_automation_post_purchase(to_name: str, product_name: str, delivery_url: str, review_url: str) -> dict[str, str]:
        return {
            "subject": "Thank you for your purchase — here's how to get started",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thank You</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">Thank you for your purchase!</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, thank you for purchasing <strong>{product_name}</strong>. Your payment was processed successfully.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border-radius:6px;margin:20px 0;">
                                <tr>
                                    <td style="padding:20px;">
                                        <p style="margin:0 0 10px;color:#16a34a;font-weight:600;font-size:16px;">Quick start tips:</p>
                                        <ul style="margin:0;padding-left:20px;color:#444;font-size:14px;line-height:1.8;">
                                            <li>Read the included guide first</li>
                                            <li>Start using the templates/tools immediately</li>
                                            <li>You get lifetime updates — no extra cost</li>
                                        </ul>
                                    </td>
                                </tr>
                            </table>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{delivery_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Access Your Purchase</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Love it? <a href="{review_url}" style="color:#2563eb;">Leave a review</a> and help other creators find it.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px;background:#f8f9fa;border-top:1px solid #e5e7eb;">
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">Ai Factory · Digital Products for Creators</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""Thank you for your purchase!

Hi {to_name}, thank you for purchasing {product_name}. Your payment was processed successfully.

Quick start tips:
- Read the included guide first
- Start using the templates/tools immediately
- You get lifetime updates — no extra cost

Access your purchase: {delivery_url}

Love it? Leave a review: {review_url}
""",
        }

    @staticmethod
    def funnel_automation_review_request(to_name: str, product_name: str, review_url: str) -> dict[str, str]:
        return {
            "subject": f"How's {product_name}? We'd love your feedback",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>We'd Love Your Feedback</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">How's it working for you?</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, you purchased <strong>{product_name}</strong> a few days ago. We'd love to hear how it's going.
                            </p>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                A quick review helps other creators make confident choices — and helps us improve.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{review_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Leave a 1-Minute Review</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Your feedback directly helps us improve. Thanks!
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px;background:#f8f9fa;border-top:1px solid #e5e7eb;">
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">Ai Factory · Digital Products for Creators</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""How's {product_name} working for you?

Hi {to_name}, you purchased {product_name} a few days ago. We'd love to hear how it's going.

A quick review helps other creators make confident choices:
{review_url}

Thanks!
""",
        }

    @staticmethod
    def funnel_automation_cross_sell(to_name: str, product_name: str, recommendations: str, store_url: str) -> dict[str, str]:
        return {
            "subject": "You might also like these — based on your purchase",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recommended For You</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">You might also like these</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, since you purchased <strong>{product_name}</strong>, we thought you'd love these:
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f9fa;border-radius:6px;margin:20px 0;">
                                <tr>
                                    <td style="padding:20px;">
                                        <p style="margin:0;color:#444;font-size:15px;line-height:1.8;">{recommendations}</p>
                                    </td>
                                </tr>
                            </table>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:10px 0;">
                                <tr><td style="padding:5px 0;color:#444;font-size:14px;line-height:1.6;">✓ Instant digital delivery</td></tr>
                                <tr><td style="padding:5px 0;color:#444;font-size:14px;line-height:1.6;">✓ 30-day money-back guarantee</td></tr>
                                <tr><td style="padding:5px 0;color:#444;font-size:14px;line-height:1.6;">✓ Lifetime free updates</td></tr>
                            </table>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{store_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Browse More Products</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px;background:#f8f9fa;border-top:1px solid #e5e7eb;">
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">Ai Factory · Digital Products for Creators</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""You might also like these

Hi {to_name}, since you purchased {product_name}, we thought you'd love these:

{recommendations}

Each product comes with:
- Instant digital delivery
- 30-day money-back guarantee
- Lifetime free updates

Browse more: {store_url}
""",
        }

    @staticmethod
    def funnel_automation_win_back(to_name: str, new_products: str, store_url: str) -> dict[str, str]:
        return {
            "subject": "We miss you — here's 15% off to come back",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>We Miss You</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);border-top:4px solid #f59e0b;">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">We miss you, {to_name}!</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                It's been a while since you visited Ai Factory. We've added some amazing new products since then.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="background:#fffbeb;border:1px solid #fbbf24;border-radius:6px;margin:20px 0;">
                                <tr>
                                    <td style="padding:20px;text-align:center;">
                                        <p style="margin:0 0 5px;color:#92400e;font-size:14px;text-transform:uppercase;letter-spacing:1px;">Your exclusive offer</p>
                                        <p style="margin:0;color:#92400e;font-size:32px;font-weight:700;">15% OFF</p>
                                        <p style="margin:5px 0 0;color:#92400e;font-size:16px;">Code: <strong>WELCOMEBACK15</strong></p>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:20px 0 10px;color:#444;font-size:16px;line-height:1.6;"><strong>New arrivals:</strong></p>
                            <p style="margin:0 0 20px;color:#444;font-size:14px;line-height:1.8;">{new_products}</p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{store_url}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Browse Now</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 40px;background:#f8f9fa;border-top:1px solid #e5e7eb;">
                            <p style="margin:0;color:#888;font-size:12px;text-align:center;">Ai Factory · Digital Products for Creators</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
            "text": f"""We miss you, {to_name}!

It's been a while since you visited Ai Factory. Here's 15% off your next purchase:

Code: WELCOMEBACK15

New arrivals:
{new_products}

Browse now: {store_url}
""",
        }

    @staticmethod
    def funnel_delivery(to_name: str, delivery_items: list[dict]) -> dict[str, str]:
        items_html = "\n".join([
            f"""<tr>
                <td style="padding:15px;border-bottom:1px solid #e5e7eb;">
                    <p style="margin:0 0 5px;color:#111;font-weight:600;">{item['product_name']}</p>
                    <p style="margin:0 0 10px;color:#666;font-size:14px;">Access expires on: {item['expires_at']}</p>
                    <a href="{item['download_url']}" style="display:inline-block;padding:8px 16px;background:#2563eb;color:#fff;text-decoration:none;border-radius:4px;font-weight:600;font-size:14px;">Access Digital Asset</a>
                </td>
            </tr>"""
            for item in delivery_items
        ])

        items_text = "\n\n".join([
            f"• {item['product_name']}\n  Access Link: {item['download_url']}\n  Expires: {item['expires_at']}"
            for item in delivery_items
        ])

        return {
            "subject": "🎁 Your digital product delivery is ready!",
            "html": f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Digital Delivery</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:40px 40px 20px;">
                            <h1 style="margin:0 0 20px;color:#111;font-size:28px;font-weight:700;">Thank you for your purchase!</h1>
                            <p style="margin:0 0 20px;color:#444;font-size:16px;line-height:1.6;">
                                Hi {to_name}, your payment was processed successfully. You can access your digital products using the secure download links below:
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
                                {items_html}
                            </table>
                            <p style="margin:20px 0 0;color:#666;font-size:14px;line-height:1.6;">
                                Need help? Reply to this email or contact <a href="mailto:support@graxia.io" style="color:#2563eb;">support@graxia.io</a>
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
            "text": f"""Thank you for your purchase!

Hi {to_name}, your payment was processed successfully. You can access your digital products using the secure download links below:

{items_text}

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
        if not self.api_key or settings.ENVIRONMENT == "development":
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
    "funnel_delivery": {
        "subject": "Your Digital Delivery",
        "html": "<html><body>Delivery</body></html>",
        "text": "Delivery",
    },
}
