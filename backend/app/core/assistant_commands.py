from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

from app.core.calendar_ops import generate_inbox_triage, generate_today_calendar_overview
from app.core.runtime_state import get_runtime_state


@dataclass(frozen=True)
class ParsedCommand:
    command: str
    args: list[str]
    raw_text: str


SUPPORTED_COMMANDS = {
    "help",
    "status",
    "today",
    "brief",
    "approvals",
    "jobs",
    "scan",
}


def parse_command_text(text: str | None) -> ParsedCommand:
    normalized = (text or "").strip()
    if not normalized:
        return ParsedCommand(command="help", args=[], raw_text="")

    if normalized.startswith("/"):
        normalized = normalized[1:]
    parts = normalized.split()
    command_token = parts[0].lower() if parts else "help"
    command = command_token.split("@", 1)[0]
    if command not in SUPPORTED_COMMANDS:
        command = "help"
    return ParsedCommand(command=command, args=parts[1:], raw_text=text or "")


def render_help_text() -> str:
    return (
        "Available commands:\n"
        "/status - runtime health, approvals, and connector state\n"
        "/today - today's calendar, inbox summary, and follow-ups\n"
        "/approvals - pending approvals queue\n"
        "/jobs - top job/freelance matches\n"
        "/brief - send the morning brief now\n"
        "/scan - trigger a manual scan\n"
        "/help - show this command list"
    )


async def execute_assistant_command(text: str | None) -> str:
    parsed = parse_command_text(text)
    if parsed.command == "status":
        return await _render_status()
    if parsed.command == "today":
        return await _render_today()
    if parsed.command == "approvals":
        return await _render_approvals()
    if parsed.command == "jobs":
        return await _render_jobs()
    if parsed.command == "brief":
        return await _trigger_brief()
    if parsed.command == "scan":
        return await _trigger_scan()
    return render_help_text()


async def _render_status() -> str:
    from sqlalchemy import desc, func, select

    from app.core.control_plane import count_pending_approvals
    from app.core.google_workspace import google_workspace
    from app.database import AsyncSessionLocal
    from app.models.automation_run import AutomationRun

    readiness = get_runtime_state()
    pending_approvals = await count_pending_approvals()
    google_health = await google_workspace.health()

    async with AsyncSessionLocal() as db:
        queued_or_running = await db.scalar(
            select(func.count()).select_from(
                select(AutomationRun)
                .where(AutomationRun.status.in_(["queued", "running"]))
                .subquery()
            )
        )
        latest_runs = list(
            (
                await db.execute(
                    select(AutomationRun)
                    .order_by(desc(AutomationRun.queued_at))
                    .limit(3)
                )
            ).scalars()
        )

    lines = [
        "System status",
        f"- Runtime: {readiness['mode']}",
        f"- Pending approvals: {pending_approvals}",
        f"- Active runs: {int(queued_or_running or 0)}",
        f"- Google Workspace: {google_health.get('status', 'unknown')}",
    ]
    issues = readiness.get("issues") or []
    if issues:
        lines.append("- Issues: " + "; ".join(str(issue) for issue in issues[:3]))
    if latest_runs:
        lines.append("- Recent runs:")
        for run in latest_runs:
            lines.append(f"  • {run.name} [{run.status}]")
    return "\n".join(lines)


async def _render_today() -> str:
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.models.job_posting import JobPosting
    from app.models.submission import Submission

    today = date.today()
    inbox_overview = await generate_inbox_triage(max_results=8)
    calendar_overview = await generate_today_calendar_overview(today, duration_minutes=30)
    calendar_summary = calendar_overview["calendar"]
    inbox_summary = inbox_overview["source"]
    triage = inbox_overview["triage"]

    async with AsyncSessionLocal() as db:
        due_submissions = list(
            (
                await db.execute(
                    select(Submission)
                    .where(
                        Submission.follow_up_date <= today,
                        Submission.status.in_(["sent", "opened"]),
                    )
                    .order_by(Submission.follow_up_date, Submission.created_at)
                    .limit(5)
                )
            ).scalars()
        )
        due_jobs = list(
            (
                await db.execute(
                    select(JobPosting)
                    .where(
                        JobPosting.follow_up_due <= today,
                        JobPosting.status.in_(["applied", "approved", "interview_scheduled", "interviewing"]),
                    )
                    .order_by(JobPosting.follow_up_due, desc(JobPosting.match_score))
                    .limit(5)
                )
            ).scalars()
        )

    lines = [f"Today ({today.isoformat()})"]
    calendar_status = str(calendar_summary.get("status") or "unknown")
    if not calendar_summary.get("configured"):
        lines.append("- Calendar: Google Workspace not configured")
    elif calendar_status != "ok":
        lines.append(f"- Calendar: {calendar_status}")
        calendar_issues = calendar_summary.get("issues") or []
        if calendar_issues:
            lines.append(f"  • issue: {str(calendar_issues[0])}")
    else:
        events = calendar_summary.get("events", [])
        lines.append(f"- Calendar events: {len(events)}")
        for event in events[:3]:
            lines.append(f"  • {event['summary']} @ {event['start']}")

    inbox_status = str(inbox_summary.get("status") or "unknown")
    if inbox_summary.get("configured") and inbox_status == "ok":
        counts = triage.get("counts") or {}
        total_count = int(inbox_summary.get("total_count") or 0)
        lines.append(
            "- Inbox: "
            + f"{int(inbox_summary.get('unread_count') or 0)} unread"
            + (f" / {total_count} recent" if total_count else "")
            + f" | action {int(counts.get('action_needed') or 0)}"
            + f" | fyi {int(counts.get('fyi') or 0)}"
            + f" | archive {int(counts.get('archive') or 0)}"
        )
        for message in triage.get("top_actions", [])[:3]:
            subject = message.get("subject") or "(no subject)"
            sender = message.get("from") or "unknown sender"
            lines.append(
                f"  • {subject} — {sender}"
                + f" [{message.get('priority', 'low')}]"
            )
    elif not inbox_summary.get("configured"):
        lines.append("- Inbox: Google Workspace not configured")
    else:
        lines.append(f"- Inbox: {inbox_status}")
        inbox_issues = inbox_summary.get("issues") or []
        if inbox_issues:
            lines.append(f"  • issue: {str(inbox_issues[0])}")

    lines.append(f"- Submission follow-ups due: {len(due_submissions)}")
    for submission in due_submissions[:3]:
        lines.append(f"  • {submission.title or 'Untitled submission'}")

    lines.append(f"- Job follow-ups due: {len(due_jobs)}")
    for job in due_jobs[:3]:
        score = float(job.match_score or 0)
        lines.append(f"  • {job.title} ({score:.0f}%)")

    suggested_slots = calendar_overview.get("suggested_slots") or []
    if suggested_slots:
        lines.append(f"- Suggested booking slots: {len(suggested_slots)}")
        for slot in suggested_slots[:2]:
            lines.append(f"  • {slot['start']} -> {slot['end']}")

    meeting_brief = calendar_overview.get("meeting_brief")
    if meeting_brief:
        lines.append("- Next meeting brief:")
        for brief_line in str(meeting_brief).splitlines()[:4]:
            lines.append(f"  • {brief_line}")

    return "\n".join(lines)


async def _render_approvals(limit: int = 5) -> str:
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.models.approval_request import ApprovalRequest

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(ApprovalRequest)
                    .where(ApprovalRequest.status == "pending")
                    .order_by(desc(ApprovalRequest.created_at))
                    .limit(limit)
                )
            ).scalars()
        )

    if not rows:
        return "No pending approvals."

    lines = [f"Pending approvals: {len(rows)}"]
    for row in rows:
        lines.append(f"- {row.title} [{row.action_type}]")
    return "\n".join(lines)


async def _render_jobs(limit: int = 5) -> str:
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.models.job_posting import JobPosting

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(JobPosting)
                    .where(JobPosting.status.in_(["discovered", "screened", "drafted", "approved", "applied"]))
                    .order_by(desc(JobPosting.match_score), desc(JobPosting.created_at))
                    .limit(limit)
                )
            ).scalars()
        )

    if not rows:
        return "No jobs in the pipeline yet."

    lines = ["Top job matches"]
    for row in rows:
        score = float(row.match_score or 0)
        company = row.company or row.source_platform or "unknown source"
        lines.append(f"- {row.title} @ {company} [{score:.0f}%] ({row.status})")
        if row.skill_gap_list:
            lines.append(f"  gaps: {', '.join(row.skill_gap_list[:3])}")
    return "\n".join(lines)


async def _trigger_brief() -> str:
    from app.agents.briefer import briefer_agent

    await briefer_agent.send_morning_brief()
    return "Morning brief triggered and sent."


async def _trigger_scan() -> str:
    from app.tasks.daily_scan import run_daily_scan
    from app.core.control_plane import (
        create_run,
        mark_run_completed,
        mark_run_failed,
        mark_run_started,
    )

    run = await create_run(
        name="Telegram/manual scan",
        task_type="daily_scan",
        trigger_source="telegram_command",
        context={"command": "/scan"},
    )

    async def _runner() -> None:
        try:
            await mark_run_started(run.id)
            result = await run_daily_scan()
            await mark_run_completed(run.id, result=result)
        except Exception as exc:
            await mark_run_failed(run.id, str(exc))

    asyncio.create_task(_runner())
    return f"Manual scan queued. Run ID: {run.id}"
