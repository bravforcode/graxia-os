import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select

from app.agents.base import BaseAgent
from app.config import settings
from app.core.tracking import sign_payload

logger = logging.getLogger(__name__)


class OutreachAgent(BaseAgent):
    name = "outreach_agent"

    def _load_template(self, name: str) -> str | None:
        try:
            from pathlib import Path

            template_path = Path(settings.IDENTITY_PATH).resolve().parent / "templates" / name
            return template_path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _render(self, template: str, mapping: dict[str, str]) -> str:
        out = template
        for key, value in mapping.items():
            out = out.replace("{{" + key + "}}", value)
        return out.strip()

    def _tracking_base(self) -> str:
        if settings.TRACKING_BASE_URL:
            return settings.TRACKING_BASE_URL.rstrip("/")
        return (settings.FRONTEND_URL or "").rstrip("/") or "http://localhost:5173"

    def _to_html(self, text: str, token: str) -> str:
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        html = escaped.replace("\n", "<br>\n")
        pixel_url = f"{self._tracking_base()}/t/open.gif?token={token}"
        return f"{html}<!--OUTREACH:{token}--><img src=\"{pixel_url}\" width=\"1\" height=\"1\" alt=\"\" />"

    def _wrap_link(self, token_payload: dict[str, str], url: str) -> str:
        token_payload = dict(token_payload)
        token_payload["target_url"] = url
        token = sign_payload(token_payload)
        return f"{self._tracking_base()}/t/click?token={token}"

    def _allowed(self, email: str) -> bool:
        email_norm = (email or "").strip().lower()
        if not email_norm:
            return False
        allowed_emails = {e.strip().lower() for e in (settings.OUTREACH_ALLOWED_EMAILS or "").split(",") if e.strip()}
        if email_norm in allowed_emails:
            return True
        domain = email_norm.split("@")[-1] if "@" in email_norm else ""
        allowed_domains = {d.strip().lower() for d in (settings.OUTREACH_ALLOWED_DOMAINS or "").split(",") if d.strip()}
        return bool(domain and domain in allowed_domains)

    def _build_message(self, contact: Any, stage: int) -> tuple[str, str, str, str, dict[str, str]]:
        profile = {}
        try:
            from app.core.identity import identity

            profile = identity.get_profile()
        except Exception:
            profile = {}

        name = profile.get("personal", {}).get("name") or "Developer"
        portfolio = profile.get("personal", {}).get("portfolio_url") or ""
        summary = profile.get("personal", {}).get("tagline") or ""
        service = profile.get("current_status", {}).get("current_positioning") or ""

        mapping = {
            "name": name,
            "contact_name": getattr(contact, "name", "") or "there",
            "company": getattr(contact, "company", "") or "",
            "role": getattr(contact, "role", "") or "",
            "portfolio": f"Portfolio: {portfolio}" if portfolio else "",
            "summary": summary,
            "service": service,
        }

        if stage == 0:
            template_name = "outreach_initial.txt"
            default_subject = f"Quick idea for {mapping['company']}" if mapping["company"] else f"Quick intro — {name}"
        elif stage == 1:
            template_name = "outreach_followup_1.txt"
            default_subject = f"Following up — {mapping['company']}" if mapping["company"] else "Following up"
        else:
            template_name = "outreach_followup_2.txt"
            default_subject = "Last quick ping"

        template = self._load_template(template_name) or ""
        body = self._render(template, mapping) if template else ""
        if not body:
            body = f"Hi {mapping['contact_name']},\n\nJust following up.\n\nBest,\n{name}"
        token_payload = {
            "contact_id": str(getattr(contact, "id", "") or ""),
            "email": str(getattr(contact, "email", "") or ""),
            "stage": str(stage),
            "template": template_name,
        }
        token = sign_payload(token_payload)
        html_body = self._to_html(body, token)
        return default_subject, body, html_body, token, token_payload

    async def run(self) -> dict[str, Any]:
        from app.database import AsyncSessionLocal
        from app.models.automation_run import AutomationRun
        from app.models.contact import Contact
        from app.models.network_interaction import NetworkInteraction
        from app.telegram_bot.bot import send_message
        from sqlalchemy import func

        max_per_day = int(settings.OUTREACH_MAX_PER_DAY or 0)
        min_days = int(settings.OUTREACH_MIN_DAYS_BETWEEN_CONTACT or 0)

        if max_per_day <= 0:
            return {"status": "skipped", "reason": "max_per_day<=0"}

        today = datetime.now(timezone.utc).date()
        cutoff_date = today - timedelta(days=min_days)

        sent = 0
        skipped = 0
        previews: list[dict[str, str]] = []
        followups_sent = 0

        async with AsyncSessionLocal() as db:
            already_sent_today = await db.scalar(
                select(func.count(NetworkInteraction.id)).where(
                    NetworkInteraction.interaction_type.in_(
                        ["email_outreach_initial", "email_outreach_followup_1", "email_outreach_followup_2"]
                    ),
                    func.date(NetworkInteraction.interaction_at) == today,
                )
            )
            remaining = max_per_day - int(already_sent_today or 0)
            if remaining <= 0:
                return {"status": "skipped", "reason": "daily_limit_reached", "sent_today": int(already_sent_today or 0)}

            campaign_key = f"outreach:{settings.OUTREACH_CAMPAIGN_NAME}:{today.isoformat()}"
            run = (
                await db.execute(
                    select(AutomationRun).where(AutomationRun.idempotency_key == campaign_key).limit(1)
                )
            ).scalar_one_or_none()
            if not run:
                run = AutomationRun(
                    name=settings.OUTREACH_CAMPAIGN_NAME,
                    task_type="outreach_campaign",
                    trigger_source="scheduler",
                    status="running",
                    idempotency_key=campaign_key,
                    context={"campaign_name": settings.OUTREACH_CAMPAIGN_NAME, "date": today.isoformat()},
                )
                db.add(run)
                await db.flush()

            due_followups = list(
                (
                    await db.execute(
                        select(Contact)
                        .where(Contact.is_deleted.is_(False))
                        .where(Contact.email.is_not(None))
                        .where(Contact.email != "")
                        .where(Contact.next_followup_date.is_not(None))
                        .where(Contact.next_followup_date <= today)
                        .order_by(desc(Contact.value_score), Contact.created_at.desc())
                        .limit(remaining * 2)
                    )
                )
                .scalars()
                .all()
            )

            for contact in due_followups:
                if sent >= remaining:
                    break
                if not self._allowed(contact.email or ""):
                    skipped += 1
                    continue
                interaction_count = await db.scalar(
                    select(func.count(NetworkInteraction.id)).where(
                        NetworkInteraction.contact_id == contact.id,
                        NetworkInteraction.interaction_type.in_(
                            ["email_outreach_initial", "email_outreach_followup_1", "email_outreach_followup_2"]
                        ),
                    )
                )
                stage = 1 if int(interaction_count or 0) <= 1 else 2
                subject, body, html_body, token, token_payload = self._build_message(contact, stage=stage)
                token_payload["campaign_id"] = str(run.id)
                token_payload["campaign_name"] = settings.OUTREACH_CAMPAIGN_NAME
                token = sign_payload(token_payload)
                html_body = self._to_html(body, token)

                if not settings.OUTREACH_AUTOSEND_ENABLED:
                    try:
                        from app.core.control_plane import queue_approval_request

                        await queue_approval_request(
                            title=f"Send outreach follow-up to {contact.email}",
                            action_type="send_email",
                            subject_type="contact",
                            subject_id=contact.id,
                            details={
                                "to": contact.email or "",
                                "subject": subject,
                                "body": body,
                                "body_html": html_body,
                                "is_html": True,
                                "headers": {"X-Outreach-Token": token},
                                "campaign_id": str(run.id),
                                "campaign_name": settings.OUTREACH_CAMPAIGN_NAME,
                                "stage": stage,
                            },
                            preview={
                                "to": contact.email or "",
                                "subject": subject,
                                "body_preview": body[:280],
                                "campaign": settings.OUTREACH_CAMPAIGN_NAME,
                                "stage": stage,
                            },
                            requested_by="outreach_agent",
                            batch_group=settings.OUTREACH_CAMPAIGN_NAME,
                        )
                        previews.append({"to": contact.email or "", "subject": subject})
                    except Exception:
                        skipped += 1
                    continue

                try:
                    from app.core.google_workspace import google_workspace

                    message_id = await google_workspace.send_message(
                        contact.email or "",
                        subject,
                        html_body,
                        is_html=True,
                        extra_headers={"X-Outreach-Token": token},
                    )
                    if not message_id:
                        skipped += 1
                        continue
                    contact.last_contacted_at = date.today()
                    if stage == 1:
                        contact.next_followup_date = today + timedelta(days=5)
                        interaction_type = "email_outreach_followup_1"
                    else:
                        contact.next_followup_date = None
                        interaction_type = "email_outreach_followup_2"
                    db.add(
                        NetworkInteraction(
                            id=uuid4(),
                            contact_id=contact.id,
                            interaction_type=interaction_type,
                            interaction_at=datetime.now(timezone.utc),
                            notes=f"campaign_id={run.id} subject={subject}",
                        )
                    )
                    sent += 1
                    followups_sent += 1
                except Exception as exc:
                    skipped += 1
                    await send_message(f"⚠️ Outreach send failed: {contact.email}\n{str(exc)[:160]}")

            query = (
                select(Contact)
                .where(Contact.is_deleted.is_(False))
                .where(Contact.email.is_not(None))
                .where(Contact.email != "")
                .where(Contact.contact_type.in_(["lead", "client", "recruiter"]))
                .order_by(desc(Contact.value_score), Contact.created_at.desc())
                .limit(max_per_day * 5)
            )
            contacts = list((await db.execute(query)).scalars().all())

            for contact in contacts:
                if sent >= remaining:
                    break
                if contact.next_followup_date is not None:
                    skipped += 1
                    continue
                if contact.last_contacted_at and contact.last_contacted_at >= cutoff_date:
                    skipped += 1
                    continue
                if not self._allowed(contact.email or ""):
                    skipped += 1
                    continue

                subject, body, html_body, token, token_payload = self._build_message(contact, stage=0)
                token_payload["campaign_id"] = str(run.id)
                token_payload["campaign_name"] = settings.OUTREACH_CAMPAIGN_NAME
                token = sign_payload(token_payload)
                html_body = self._to_html(body, token)

                if not settings.OUTREACH_AUTOSEND_ENABLED:
                    try:
                        from app.core.control_plane import queue_approval_request

                        await queue_approval_request(
                            title=f"Send outreach email to {contact.email}",
                            action_type="send_email",
                            subject_type="contact",
                            subject_id=contact.id,
                            details={
                                "to": contact.email or "",
                                "subject": subject,
                                "body": body,
                                "body_html": html_body,
                                "is_html": True,
                                "headers": {"X-Outreach-Token": token},
                                "campaign_id": str(run.id),
                                "campaign_name": settings.OUTREACH_CAMPAIGN_NAME,
                                "stage": 0,
                            },
                            preview={
                                "to": contact.email or "",
                                "subject": subject,
                                "body_preview": body[:280],
                                "campaign": settings.OUTREACH_CAMPAIGN_NAME,
                                "stage": 0,
                            },
                            requested_by="outreach_agent",
                            batch_group=settings.OUTREACH_CAMPAIGN_NAME,
                        )
                        previews.append({"to": contact.email or "", "subject": subject})
                    except Exception:
                        skipped += 1
                    continue

                try:
                    from app.core.google_workspace import google_workspace

                    message_id = await google_workspace.send_message(
                        contact.email or "",
                        subject,
                        html_body,
                        is_html=True,
                        extra_headers={"X-Outreach-Token": token},
                    )
                    if not message_id:
                        skipped += 1
                        continue
                    contact.last_contacted_at = date.today()
                    contact.next_followup_date = today + timedelta(days=3)
                    db.add(
                        NetworkInteraction(
                            id=uuid4(),
                            contact_id=contact.id,
                            interaction_type="email_outreach_initial",
                            interaction_at=datetime.now(timezone.utc),
                            notes=f"campaign_id={run.id} subject={subject}",
                        )
                    )
                    sent += 1
                except Exception as exc:
                    skipped += 1
                    await send_message(f"⚠️ Outreach send failed: {contact.email}\n{str(exc)[:160]}")

            await db.commit()

        if sent > 0 or previews:
            lines = [
                "📮 Outreach",
                f"• Sent: {sent}",
                f"• Followups: {followups_sent}",
                f"• Skipped: {skipped}",
            ]
            if previews:
                lines.append("Previews:")
                for p in previews[:5]:
                    lines.append(f"• {p['to']} — {p['subject']}")
            await send_message("\n".join(lines))

        try:
            async with AsyncSessionLocal() as db:
                run_row = await db.get(AutomationRun, run.id) if "run" in locals() and run else None
                if run_row:
                    run_row.status = "completed"
                    run_row.result = {"sent": sent, "followups": followups_sent, "skipped": skipped}
                    run_row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass

        return {"status": "ok", "sent": sent, "skipped": skipped, "previews": previews}


outreach_agent = OutreachAgent()
