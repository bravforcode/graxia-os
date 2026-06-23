"""Verify human approval payload against a DemoCanaryPlan."""
from execution.demo_canary.approval_payload import ApprovalPayload
from execution.demo_canary.canary_plan import DemoCanaryPlan

class ApprovalVerifier:
    """Verifies approval payload matches canary plan."""

    def __init__(self):
        self._used_nonces = set()

    def verify(self, plan: DemoCanaryPlan, approval: ApprovalPayload) -> tuple[bool, str]:
        """Verify approval is valid for this plan. Returns (passed, reason)."""
        if not plan or not plan.canary_id:
            return False, "No canary plan provided"

        if approval.canary_id != plan.canary_id:
            return False, f"Approval canary_id {approval.canary_id} != plan {plan.canary_id}"

        if approval.plan_hash and approval.plan_hash != plan.plan_hash:
            return False, "Approval plan hash does not match plan"

        if approval.environment != "PEPPERSTONE_DEMO_ONLY":
            return False, f"Approval environment is {approval.environment}, not DEMO"

        if approval.is_expired():
            return False, "Approval has expired"

        if approval.approval_nonce in self._used_nonces:
            return False, "Approval nonce already used (replay detected)"

        self._used_nonces.add(approval.approval_nonce)
        return True, ""
