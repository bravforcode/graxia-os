from __future__ import annotations

import re
from typing import Any

from .capabilities import WorkerCapabilityResult

_SECRET_PATTERNS = [
    re.compile(r"\b(tok_[A-Za-z0-9_\-]+)\b", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]+)\b", re.IGNORECASE),
    re.compile(r"\b(api[_-]?key\s*[:=]?\s*[A-Za-z0-9_\-]+)\b", re.IGNORECASE),
]

_DANGEROUS_TOOLS = {
    "change_stripe_secret_config",
    "delete_database",
    "deploy_production",
    "force_push",
    "print_secrets",
    "read_env",
    "rotate_keys",
}

_APPROVAL_TOOLS = {
    "create_calendar_event",
    "move_file",
    "send_email",
    "share_file",
}


class RuntimeWorkerMockProvider:
    """Deterministic worker provider for local/runtime-safe execution."""

    def summarize_order(self, payload: dict[str, Any]) -> WorkerCapabilityResult:
        order_id = str(payload.get("order_id") or "unknown-order")
        customer_name = str(payload.get("customer_name") or "customer")
        currency = str(payload.get("currency") or "USD")
        total = payload.get("total") or 0
        items = payload.get("items") or []
        item_count = len(items)
        return WorkerCapabilityResult(
            ok=True,
            risk_level="READ_ONLY",
            approval_required=False,
            data={
                "summary": f"Order {order_id} for {customer_name} totals {currency} {total} across {item_count} line items.",
                "item_count": item_count,
                "order_id": order_id,
            },
        )

    def draft_customer_reply(self, payload: dict[str, Any]) -> WorkerCapabilityResult:
        customer_name = str(payload.get("customer_name") or "Customer")
        subject = str(payload.get("subject") or "Follow-up")
        customer_message = str(payload.get("customer_message") or "").strip()
        draft_body = (
            f"Hi {customer_name},\n\n"
            f"Thanks for your note about '{subject}'. "
            "I drafted a response that addresses the request and confirms next steps.\n\n"
            f"Customer context: {customer_message[:180]}\n\n"
            "Please review before sending."
        )
        return WorkerCapabilityResult(
            ok=True,
            risk_level="APPROVAL_REQUIRED",
            approval_required=True,
            data={
                "channel": "customer_reply",
                "draft_body": draft_body,
                "subject": subject,
            },
        )

    def classify_lead(self, payload: dict[str, Any]) -> WorkerCapabilityResult:
        source = str(payload.get("source") or "unknown")
        score = int(payload.get("score") or 0)
        tier = "cold"
        if score >= 80:
            tier = "hot"
        elif score >= 50:
            tier = "warm"
        return WorkerCapabilityResult(
            ok=True,
            risk_level="READ_ONLY",
            approval_required=False,
            data={
                "source": source,
                "score": score,
                "classification": tier,
            },
        )

    def prepare_recommendation(self, payload: dict[str, Any]) -> WorkerCapabilityResult:
        bottleneck = str(payload.get("bottleneck") or "unknown bottleneck")
        target_metric = str(payload.get("target_metric") or "conversion rate")
        return WorkerCapabilityResult(
            ok=True,
            risk_level="APPROVAL_REQUIRED",
            approval_required=True,
            data={
                "recommendation_type": "operator_brief",
                "summary": f"Address {bottleneck} to improve {target_metric}.",
            },
        )

    def write_memory_draft(self, payload: dict[str, Any]) -> WorkerCapabilityResult:
        content = self._redact_sensitive(str(payload.get("content") or ""))
        title = str(payload.get("title") or "Memory Draft")
        tags = list(payload.get("tags") or [])
        return WorkerCapabilityResult(
            ok=True,
            risk_level="LOW_WRITE",
            approval_required=False,
            data={
                "title": title,
                "content": content,
                "tags": tags,
                "category": "vault_note",
                "write_mode": "draft_only",
            },
        )

    def propose_tool_call(self, payload: dict[str, Any]) -> WorkerCapabilityResult:
        tool_name = str(payload.get("tool_name") or "").strip()
        arguments = dict(payload.get("arguments") or {})
        if tool_name in _DANGEROUS_TOOLS:
            return WorkerCapabilityResult(
                ok=False,
                risk_level="DANGEROUS_BLOCKED",
                approval_required=False,
                error={
                    "code": "DANGEROUS_TOOL_BLOCKED",
                    "message": f"Dangerous tool blocked: {tool_name}",
                },
            )
        approval_required = tool_name in _APPROVAL_TOOLS
        risk_level: Any = "READ_ONLY"
        if approval_required:
            risk_level = "APPROVAL_REQUIRED"
        elif tool_name.startswith(("create_", "update_", "write_")):
            risk_level = "LOW_WRITE"
        return WorkerCapabilityResult(
            ok=True,
            risk_level=risk_level,
            approval_required=approval_required,
            data={
                "tool_name": tool_name,
                "arguments": arguments,
                "execution_mode": "proposal_only",
            },
        )

    def _redact_sensitive(self, content: str) -> str:
        sanitized = content
        for pattern in _SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized
