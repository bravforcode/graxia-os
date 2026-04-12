from app.core.inbox_ops import classify_message_priority, triage_inbox_messages


def test_classify_message_priority_detects_urgent_action_items():
    message = {
        "subject": "Urgent: proposal needed today",
        "snippet": "Please send the revised quote before EOD.",
        "from": "Client <client@example.com>",
    }

    result = classify_message_priority(message)

    assert result.category == "action_needed"
    assert result.priority == "high"
    assert "urgent" in result.reasons
    assert "proposal" in result.reasons


def test_triage_inbox_messages_groups_messages_and_counts_actions():
    messages = [
        {
            "subject": "Interview schedule confirmation",
            "snippet": "Can you confirm tomorrow 10am?",
            "from": "Recruiter <r@example.com>",
        },
        {
            "subject": "Weekly newsletter",
            "snippet": "Top startup news this week.",
            "from": "News <n@example.com>",
        },
        {
            "subject": "Follow up on proposal",
            "snippet": "Checking if you had time to review.",
            "from": "Prospect <p@example.com>",
        },
    ]

    summary = triage_inbox_messages(messages)

    assert summary["counts"]["action_needed"] == 2
    assert summary["counts"]["archive"] == 1
    assert summary["top_actions"][0]["category"] == "action_needed"
    assert summary["top_actions"][1]["category"] == "action_needed"
