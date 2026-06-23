"""Test canary plan and approval boundary."""
import pytest
from decimal import Decimal
from execution.demo_canary.canary_plan import DemoCanaryPlan, PEPPERSTONE_DEMO_ONLY
from execution.demo_canary.approval_payload import ApprovalPayload
from execution.demo_canary.approval_verifier import ApprovalVerifier

class TestDemoCanaryPlan:
    def test_plan_immutable(self):
        plan = DemoCanaryPlan(canary_id="CANARY-001")
        assert plan.environment == PEPPERSTONE_DEMO_ONLY

    def test_plan_hash_deterministic(self):
        plan1 = DemoCanaryPlan(canary_id="CANARY-001")
        plan2 = DemoCanaryPlan(canary_id="CANARY-001")
        assert plan1.plan_hash == plan2.plan_hash

    def test_different_ids_different_hashes(self):
        plan1 = DemoCanaryPlan(canary_id="CANARY-001")
        plan2 = DemoCanaryPlan(canary_id="CANARY-002")
        assert plan1.plan_hash != plan2.plan_hash

    def test_strategy_hash_must_be_none(self):
        with pytest.raises(ValueError):
            DemoCanaryPlan(canary_id="CANARY-001", strategy_hash="some_hash")

    def test_non_xauusd_rejected(self):
        with pytest.raises(ValueError):
            DemoCanaryPlan(canary_id="CANARY-001", symbol="EURUSD")

    def test_negative_volume_rejected(self):
        with pytest.raises(ValueError):
            DemoCanaryPlan(canary_id="CANARY-001", volume=Decimal("-0.01"))


class TestApprovalVerifier:
    def test_valid_approval_passes(self):
        plan = DemoCanaryPlan(canary_id="CANARY-001")
        approval = ApprovalPayload(
            canary_id="CANARY-001",
            plan_hash=plan.plan_hash,
            environment="PEPPERSTONE_DEMO_ONLY",
            approval_nonce=ApprovalPayload.generate_nonce(),
        )
        verifier = ApprovalVerifier()
        passed, reason = verifier.verify(plan, approval)
        assert passed, reason

    def test_wrong_canary_id_rejected(self):
        plan = DemoCanaryPlan(canary_id="CANARY-001")
        approval = ApprovalPayload(canary_id="CANARY-WRONG")
        verifier = ApprovalVerifier()
        passed, reason = verifier.verify(plan, approval)
        assert not passed

    def test_replay_nonce_rejected(self):
        plan = DemoCanaryPlan(canary_id="CANARY-001")
        nonce = ApprovalPayload.generate_nonce()
        approval = ApprovalPayload(
            canary_id="CANARY-001", plan_hash=plan.plan_hash,
            environment="PEPPERSTONE_DEMO_ONLY", approval_nonce=nonce,
        )
        verifier = ApprovalVerifier()
        passed1, _ = verifier.verify(plan, approval)
        assert passed1
        passed2, reason = verifier.verify(plan, approval)
        assert not passed2
