from datetime import date

from app.core.calendar_ops import build_meeting_brief, suggest_booking_slots


def test_suggest_booking_slots_avoids_existing_events_and_prefers_evening():
    events = [
        {
            "summary": "Morning standup",
            "start": "2026-04-03T18:00:00+07:00",
            "end": "2026-04-03T18:30:00+07:00",
        }
    ]

    slots = suggest_booking_slots(
        target_date=date(2026, 4, 3),
        events=events,
        duration_minutes=30,
        best_work_hours="evening and weekend",
        max_slots=3,
    )

    assert len(slots) == 3
    assert slots[0]["start"] == "2026-04-03T18:30:00+07:00"
    assert slots[0]["end"] == "2026-04-03T19:00:00+07:00"


def test_suggest_booking_slots_blocks_all_day_events():
    events = [
        {
            "summary": "Offsite",
            "start": "2026-04-03",
            "end": "2026-04-04",
        }
    ]

    slots = suggest_booking_slots(
        target_date=date(2026, 4, 3),
        events=events,
        duration_minutes=30,
        best_work_hours="evening and weekend",
        max_slots=3,
    )

    assert slots == []


def test_suggest_booking_slots_treats_naive_times_as_bangkok():
    events = [
        {
            "summary": "Call",
            "start": "2026-04-03T18:00:00",
            "end": "2026-04-03T18:30:00",
        }
    ]

    slots = suggest_booking_slots(
        target_date=date(2026, 4, 3),
        events=events,
        duration_minutes=30,
        best_work_hours="evening and weekend",
        max_slots=1,
    )

    assert slots[0]["start"] == "2026-04-03T18:30:00+07:00"


def test_build_meeting_brief_includes_contact_and_pipeline_context():
    event = {
        "summary": "Call with Acme",
        "start": "2026-04-03T19:00:00+07:00",
        "attendees": [{"email": "ceo@acme.com", "display_name": "Jane CEO"}],
        "description": "Discuss automation dashboard proposal",
    }
    context = {
        "contacts": [
            {
                "name": "Jane CEO",
                "company": "Acme",
                "role": "Founder",
                "notes": "Interested in automation dashboard",
            }
        ],
        "submissions": [
            {
                "title": "Acme dashboard proposal",
                "status": "sent",
            }
        ],
        "jobs": [],
    }

    brief = build_meeting_brief(event, context)

    assert "Acme" in brief
    assert "Jane CEO" in brief
    assert "Acme dashboard proposal" in brief
    assert "Discuss automation dashboard proposal" in brief
