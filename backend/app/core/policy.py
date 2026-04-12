from dataclasses import dataclass


@dataclass(frozen=True)
class ActionPolicy:
    action_type: str
    requires_approval: bool
    batchable: bool
    default_ttl_hours: int
    policy_class: str


_DEFAULT_POLICY = ActionPolicy(
    action_type="default",
    requires_approval=True,
    batchable=False,
    default_ttl_hours=24,
    policy_class="approval_required",
)

_POLICIES: dict[str, ActionPolicy] = {
    "draft_review": ActionPolicy(
        action_type="draft_review",
        requires_approval=True,
        batchable=True,
        default_ttl_hours=24,
        policy_class="approval_required",
    ),
    "job_apply_submit": ActionPolicy(
        action_type="job_apply_submit",
        requires_approval=True,
        batchable=True,
        default_ttl_hours=24,
        policy_class="approval_required",
    ),
    "competition_submit": ActionPolicy(
        action_type="competition_submit",
        requires_approval=True,
        batchable=True,
        default_ttl_hours=24,
        policy_class="approval_required",
    ),
    "network_message_send": ActionPolicy(
        action_type="network_message_send",
        requires_approval=True,
        batchable=True,
        default_ttl_hours=24,
        policy_class="approval_required",
    ),
    "content_publish": ActionPolicy(
        action_type="content_publish",
        requires_approval=True,
        batchable=True,
        default_ttl_hours=24,
        policy_class="approval_required",
    ),
    "calendar_external_booking": ActionPolicy(
        action_type="calendar_external_booking",
        requires_approval=True,
        batchable=False,
        default_ttl_hours=12,
        policy_class="approval_required",
    ),
    "engineering_prod_change": ActionPolicy(
        action_type="engineering_prod_change",
        requires_approval=True,
        batchable=False,
        default_ttl_hours=12,
        policy_class="approval_required",
    ),
    "engineering_non_prod_change": ActionPolicy(
        action_type="engineering_non_prod_change",
        requires_approval=False,
        batchable=False,
        default_ttl_hours=0,
        policy_class="auto_allowed",
    ),
    "internal_sync": ActionPolicy(
        action_type="internal_sync",
        requires_approval=False,
        batchable=False,
        default_ttl_hours=0,
        policy_class="auto_allowed",
    ),
}


def get_action_policy(action_type: str) -> ActionPolicy:
    return _POLICIES.get(action_type, _DEFAULT_POLICY)


def build_batch_key(
    action_type: str,
    subject_type: str | None = None,
    group_key: str | None = None,
) -> str | None:
    parts = [action_type]
    if subject_type:
        parts.append(subject_type)
    if group_key:
        parts.append(group_key)
    return ":".join(parts) if parts else None
