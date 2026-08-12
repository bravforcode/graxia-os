"""Tests for safe runtime test data factory."""
from __future__ import annotations

import pytest
from app.beta.synthetic_tester.test_data import (
    FACTORY_REGISTRY,
    generate_test_data,
    make_test_organization,
    make_test_user,
    make_test_operator,
    make_test_beta_tester_hash,
    make_test_auth_context,
    make_wrong_org_auth_context,
    make_missing_permission_auth_context,
    make_test_opportunity_payload,
    make_test_content_draft_payload,
    make_test_feedback_payload,
    make_oversized_feedback_payload,
    make_prompt_injection_feedback_payload,
    make_dangerous_tool_params,
    make_test_mcp_params,
    make_cross_org_mcp_params,
    make_test_workflow_params,
    make_cross_org_workflow_params,
    make_kill_switch_state,
)


class TestTestDataFactory:
    def test_organization_has_test_prefix(self):
        org = make_test_organization()
        assert org["id"].startswith("org_test_")
        assert org["is_test"] is True

    def test_user_has_test_prefix(self):
        user = make_test_user()
        assert user["id"].startswith("user_test_")
        assert user["email"].endswith("@example.test")
        assert user["is_test"] is True

    def test_operator_has_test_prefix(self):
        op = make_test_operator()
        assert op["id"].startswith("op_test_")
        assert op["role"] == "operator"
        assert op["beta_tester"] is True

    def test_beta_tester_hash_contains_no_raw(self):
        h = make_test_beta_tester_hash()
        assert h["is_test"] is True
        assert "..." in h["raw_prefix"]  # truncated
        assert h["hash"].startswith("sha256$mock$")

    def test_auth_context_default(self):
        ctx = make_test_auth_context()
        assert ctx["user_id"].startswith("user_test_")
        assert ctx["organization_id"].startswith("org_test_")
        assert ctx["is_test"] is True

    def test_wrong_org_auth(self):
        ctx = make_wrong_org_auth_context()
        assert ctx["organization_id"] == "org_test_attacker_0001"

    def test_missing_permission_auth(self):
        ctx = make_missing_permission_auth_context()
        assert "approve:draft" not in ctx["permissions"]

    def test_opportunity_is_test(self):
        payload = make_test_opportunity_payload()
        assert payload["title"].startswith("[TEST]")
        assert payload["is_test"] is True

    def test_content_draft_is_draft_only(self):
        payload = make_test_content_draft_payload()
        assert payload["is_test"] is True
        assert payload["draft_only"] is True

    def test_feedback_payload(self):
        payload = make_test_feedback_payload()
        assert payload["is_test"] is True
        assert "[AI TESTER]" in payload["comment"]

    def test_oversized_feedback(self):
        payload = make_oversized_feedback_payload()
        assert len(payload["comment"]) == 100_000

    def test_prompt_injection_feedback(self):
        payload = make_prompt_injection_feedback_payload()
        assert "productionReady" in payload["comment"]
        assert "Ignore previous" in payload["comment"]

    def test_dangerous_tool_params(self):
        params = make_dangerous_tool_params()
        assert params["tool"] == "send_email"
        assert params["is_test"] is True

    def test_mcp_params(self):
        params = make_test_mcp_params()
        assert params["tool"] == "read_opportunity"
        assert params["arguments"]["is_test"] is True

    def test_cross_org_mcp(self):
        params = make_cross_org_mcp_params()
        assert params["arguments"]["organization_id"] == "org_test_attacker_9999"

    def test_workflow_params_draft_only(self):
        params = make_test_workflow_params()
        assert params["params"]["draft_only"] is True

    def test_cross_org_workflow(self):
        params = make_cross_org_workflow_params()
        assert params["organization_id"] == "org_test_attacker_9999"

    def test_kill_switch_state(self):
        state = make_kill_switch_state()
        assert state["kill_switch_active"] is True
        assert state["is_test"] is True

    def test_factory_registry_contains_all(self):
        expected_keys = {
            "organization", "user", "operator", "beta_tester_hash",
            "auth_context", "wrong_org_auth", "missing_permission_auth",
            "opportunity", "content_draft", "feedback",
            "oversized_feedback", "prompt_injection_feedback",
            "dangerous_tool", "mcp_params", "cross_org_mcp",
            "workflow_params", "cross_org_workflow", "kill_switch",
        }
        assert expected_keys.issubset(set(FACTORY_REGISTRY.keys()))

    def test_generate_test_data_by_kind(self):
        org = generate_test_data("organization")
        assert org["is_test"] is True
        feedback = generate_test_data("feedback")
        assert feedback["is_test"] is True

    def test_generate_test_data_unknown_kind(self):
        with pytest.raises(ValueError, match="Unknown test data kind"):
            generate_test_data("nonexistent")

    def test_no_real_pii_in_email(self):
        user = make_test_user()
        assert "@example.test" in user["email"]
        assert "gmail.com" not in user["email"]
        assert "yahoo.com" not in user["email"]

    def test_no_real_pii_in_operator(self):
        op = make_test_operator()
        assert "@example.test" in op["email"]

    def test_auth_context_deterministic_default(self):
        ctx1 = make_test_auth_context()
        ctx2 = make_test_auth_context()
        # Different UUIDs each call
        assert ctx1["user_id"] != ctx2["user_id"]

    def test_opportunity_no_real_data(self):
        payload = make_test_opportunity_payload()
        assert "[TEST]" in payload["title"]
        assert "synthetic" in payload["description"].lower()
