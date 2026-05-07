from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HIGH_PRIORITY_KEYWORDS = {
    "urgent",
    "asap",
    "today",
    "deadline",
    "confirm",
    "interview",
    "proposal",
    "quote",
    "invoice",
    "payment",
    "meeting",
    "schedule",
    "review",
}
LOW_SIGNAL_KEYWORDS = {
    "newsletter",
    "digest",
    "promo",
    "promotion",
    "unsubscribe",
    "sale",
    "news",
}
FOLLOW_UP_KEYWORDS = {
    "follow up",
    "checking in",
    "circling back",
    "reviewed",
    "reply",
    "update",
}


@dataclass(frozen=True)
class InboxPriorityResult:
    category: str
    priority: str
    reasons: list[str]


def _message_text(message: dict[str, Any]) -> str:
    parts = [
        str(message.get("subject") or ""),
        str(message.get("snippet") or ""),
        str(message.get("from") or ""),
    ]
    return " ".join(parts).strip().lower()


def classify_message_priority(message: dict[str, Any]) -> InboxPriorityResult:
    text = _message_text(message)
    reasons: list[str] = []

    if any(keyword in text for keyword in LOW_SIGNAL_KEYWORDS):
        return InboxPriorityResult(category="archive", priority="low", reasons=["low_signal"])

    if any(keyword in text for keyword in FOLLOW_UP_KEYWORDS):
        reasons.append("follow_up")

    for keyword in HIGH_PRIORITY_KEYWORDS:
        if keyword in text:
            reasons.append(keyword)

    if any(reason in {"urgent", "today", "deadline", "interview", "proposal", "payment"} for reason in reasons):
        return InboxPriorityResult(category="action_needed", priority="high", reasons=list(dict.fromkeys(reasons)))

    if reasons:
        return InboxPriorityResult(category="action_needed", priority="medium", reasons=list(dict.fromkeys(reasons)))

    return InboxPriorityResult(category="fyi", priority="low", reasons=["general"])


def triage_inbox_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"action_needed": 0, "fyi": 0, "archive": 0}
    top_actions: list[dict[str, Any]] = []
    classified_messages: list[dict[str, Any]] = []

    priority_rank = {"high": 0, "medium": 1, "low": 2}

    for message in messages:
        priority = classify_message_priority(message)
        counts[priority.category] += 1
        enriched = {
            **message,
            "category": priority.category,
            "priority": priority.priority,
            "reasons": priority.reasons,
        }
        classified_messages.append(enriched)
        if priority.category == "action_needed":
            top_actions.append(enriched)

    top_actions.sort(
        key=lambda item: (
            priority_rank.get(str(item.get("priority") or "low"), 2),
            str(item.get("subject") or ""),
        )
    )

    return {
        "counts": counts,
        "top_actions": top_actions[:5],
        "messages": classified_messages,
    }
