from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.google_workspace import google_workspace
from app.core.identity import identity


def _parse_event_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value:
        return None
    timezone = ZoneInfo("Asia/Bangkok")
    try:
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            parsed_date = date.fromisoformat(value)
            return datetime.combine(parsed_date, time.min, tzinfo=timezone)
    except ValueError:
        return None

    value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed


def _windows_for_day(target_date: date, best_work_hours: str) -> list[tuple[datetime, datetime]]:
    timezone = ZoneInfo("Asia/Bangkok")
    lowered = (best_work_hours or "").lower()
    windows: list[tuple[datetime, datetime]] = []

    if target_date.weekday() >= 5:
        windows.append(
            (
                datetime.combine(target_date, time(10, 0), tzinfo=timezone),
                datetime.combine(target_date, time(17, 0), tzinfo=timezone),
            )
        )
        return windows

    if "evening" in lowered:
        windows.append(
            (
                datetime.combine(target_date, time(18, 0), tzinfo=timezone),
                datetime.combine(target_date, time(21, 0), tzinfo=timezone),
            )
        )
    else:
        windows.append(
            (
                datetime.combine(target_date, time(9, 0), tzinfo=timezone),
                datetime.combine(target_date, time(17, 0), tzinfo=timezone),
            )
        )
    return windows


def suggest_booking_slots(
    target_date: date,
    events: list[dict[str, Any]],
    duration_minutes: int,
    best_work_hours: str,
    max_slots: int = 5,
) -> list[dict[str, str]]:
    windows = _windows_for_day(target_date, best_work_hours)
    window_timezone = windows[0][0].tzinfo if windows else ZoneInfo("Asia/Bangkok")
    busy_ranges: list[tuple[datetime, datetime]] = []
    for event in events:
        start = _parse_event_datetime(str(event.get("start") or ""))
        end = _parse_event_datetime(str(event.get("end") or ""))
        if start and end:
            if start.tzinfo is None:
                start = start.replace(tzinfo=window_timezone)
            else:
                start = start.astimezone(window_timezone)
            if end.tzinfo is None:
                end = end.replace(tzinfo=window_timezone)
            else:
                end = end.astimezone(window_timezone)
            if end > start:
                busy_ranges.append((start, end))
    busy_ranges.sort(key=lambda item: item[0])

    duration = timedelta(minutes=duration_minutes)
    slots: list[dict[str, str]] = []
    for window_start, window_end in windows:
        cursor = window_start
        for busy_start, busy_end in busy_ranges:
            if busy_end <= cursor or busy_start >= window_end:
                continue
            if busy_start - cursor >= duration:
                slots.append(
                    {
                        "start": cursor.isoformat(),
                        "end": (cursor + duration).isoformat(),
                    }
                )
                if len(slots) >= max_slots:
                    return slots
            if busy_end > cursor:
                cursor = busy_end
        while cursor + duration <= window_end and len(slots) < max_slots:
            slots.append(
                {
                    "start": cursor.isoformat(),
                    "end": (cursor + duration).isoformat(),
                }
            )
            cursor += duration
        if len(slots) >= max_slots:
            return slots
    return slots


def build_meeting_brief(event: dict[str, Any], context: dict[str, Any]) -> str:
    summary = str(event.get("summary") or "(no title)")
    start = str(event.get("start") or "")
    description = str(event.get("description") or "").strip()
    contacts = context.get("contacts") or []
    submissions = context.get("submissions") or []
    jobs = context.get("jobs") or []

    lines = [f"Meeting brief: {summary}", f"Start: {start}"]
    if contacts:
        primary_contact = contacts[0]
        lines.append(
            "People: "
            + f"{primary_contact.get('name', 'Unknown')} ({primary_contact.get('role', 'unknown role')} @ {primary_contact.get('company', 'unknown company')})"
        )
        if primary_contact.get("notes"):
            lines.append(f"Context: {primary_contact['notes']}")
    if description:
        lines.append(f"Agenda hint: {description}")
    if submissions:
        lines.append("Pipeline context: " + ", ".join(str(item.get("title") or "") for item in submissions[:2] if item.get("title")))
    if jobs:
        lines.append("Related jobs: " + ", ".join(str(item.get("title") or "") for item in jobs[:2] if item.get("title")))
    if len(lines) == 2 and not description:
        lines.append("No additional CRM or pipeline context found yet.")
    return "\n".join(lines)


async def generate_inbox_triage(max_results: int = 10) -> dict[str, Any]:
    from app.core.inbox_ops import triage_inbox_messages

    inbox_summary = await google_workspace.get_gmail_inbox_summary(max_results=max_results)
    messages = list(inbox_summary.get("messages") or [])
    triage = triage_inbox_messages(messages)
    return {
        "source": inbox_summary,
        "triage": triage,
    }


async def generate_today_calendar_overview(
    target_date: date | None = None,
    duration_minutes: int = 30,
) -> dict[str, Any]:
    selected_date = target_date or date.today()
    calendar_summary = await google_workspace.get_calendar_day_summary(selected_date, max_results=10)
    events = list(calendar_summary.get("events") or [])
    profile = identity.get_profile()
    current_status = profile.get("current_status") or {}
    best_work_hours = str(current_status.get("best_work_hours") or "evening and weekend")
    suggested_slots: list[dict[str, str]] = []
    if calendar_summary.get("configured") and calendar_summary.get("status") == "ok":
        suggested_slots = suggest_booking_slots(
            target_date=selected_date,
            events=events,
            duration_minutes=duration_minutes,
            best_work_hours=best_work_hours,
            max_slots=5,
        )

    next_event = events[0] if events else None
    meeting_brief = None
    if next_event is not None:
        context = await _load_meeting_context(next_event)
        meeting_brief = build_meeting_brief(next_event, context)

    return {
        "calendar": calendar_summary,
        "suggested_slots": suggested_slots,
        "meeting_brief": meeting_brief,
        "best_work_hours": best_work_hours,
    }


async def _load_meeting_context(event: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import desc, or_, select

    from app.database import AsyncSessionLocal
    from app.models.contact import Contact
    from app.models.job_posting import JobPosting
    from app.models.submission import Submission

    summary = str(event.get("summary") or "").strip()
    description = str(event.get("description") or "").strip()
    attendee_emails = [
        str(attendee.get("email") or "").strip().lower()
        for attendee in (event.get("attendees") or [])
        if isinstance(attendee, dict) and attendee.get("email")
    ]

    async with AsyncSessionLocal() as db:
        contacts_query = select(Contact).order_by(desc(Contact.updated_at)).limit(3)
        filters = []
        if attendee_emails:
            filters.append(Contact.email.in_(attendee_emails))
        if summary:
            like_summary = f"%{summary[:40]}%"
            filters.append(or_(Contact.name.ilike(like_summary), Contact.company.ilike(like_summary)))
        if filters:
            contacts_query = contacts_query.where(or_(*filters))
        contacts = list((await db.execute(contacts_query)).scalars().all())

        submissions_query = (
            select(Submission)
            .order_by(desc(Submission.updated_at))
            .limit(3)
        )
        if summary:
            like_summary = f"%{summary[:40]}%"
            submissions_query = submissions_query.where(
                or_(
                    Submission.title.ilike(like_summary),
                    Submission.content.ilike(like_summary),
                    Submission.subject_line.ilike(like_summary),
                )
            )
        submissions = list((await db.execute(submissions_query)).scalars().all())

        jobs_query = select(JobPosting).order_by(desc(JobPosting.updated_at)).limit(3)
        if summary:
            like_summary = f"%{summary[:40]}%"
            job_filters = [
                JobPosting.title.ilike(like_summary),
                JobPosting.company.ilike(like_summary),
            ]
            if description:
                job_filters.append(JobPosting.description.ilike(f"%{description[:40]}%"))
            jobs_query = jobs_query.where(or_(*job_filters))
        jobs = list((await db.execute(jobs_query)).scalars().all())

    return {
        "contacts": [
            {
                "name": contact.name,
                "company": contact.company,
                "role": contact.role,
                "notes": contact.notes,
            }
            for contact in contacts
        ],
        "submissions": [
            {
                "title": submission.title,
                "status": submission.status,
            }
            for submission in submissions
        ],
        "jobs": [
            {
                "title": job.title,
                "company": job.company,
                "status": job.status,
            }
            for job in jobs
        ],
    }
