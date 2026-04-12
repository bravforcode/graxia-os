from app.core.policy import build_batch_key, get_action_policy


def test_draft_review_requires_approval_and_is_batchable():
    policy = get_action_policy("draft_review")

    assert policy.requires_approval is True
    assert policy.batchable is True
    assert policy.default_ttl_hours == 24


def test_engineering_non_prod_change_can_auto_run():
    policy = get_action_policy("engineering_non_prod_change")

    assert policy.requires_approval is False
    assert policy.batchable is False


def test_unknown_actions_fall_back_to_conservative_policy():
    policy = get_action_policy("unrecognized_action")

    assert policy.requires_approval is True
    assert policy.policy_class == "approval_required"


def test_batch_key_is_stable_and_compact():
    batch_key = build_batch_key(
        action_type="draft_review",
        subject_type="content_draft",
        group_key="proposal",
    )

    assert batch_key == "draft_review:content_draft:proposal"
