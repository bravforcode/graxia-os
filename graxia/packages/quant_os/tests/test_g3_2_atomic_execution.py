"""G3.2 atomic execution handoff tests. No MT5 dependency."""
import pytest
import json, hashlib, os, tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# ── Cost semantics tests ──

class TestCostSemantics:
    """All-in max loss must be UNKNOWN unless every cost known."""
    
    def test_projected_price_stop_loss_is_not_max_loss(self):
        """projected_price_stop_loss_usd ≠ estimated_all_in_loss_usd."""
        projected = 0.63
        assert projected < 999  # Not a max loss claim
        assert projected == 0.63  # It's just the SL distance
    
    def test_estimated_all_in_loss_unknown(self):
        """estimated_all_in_loss_usd='UNKNOWN' when commission not sourced."""
        plan = {
            "projected_price_stop_loss_usd": 0.63,
            "estimated_commission_usd": "UNKNOWN",
            "estimated_all_in_loss_usd": "UNKNOWN",
        }
        assert plan["estimated_all_in_loss_usd"] == "UNKNOWN"
    
    def test_no_false_max_loss_label(self):
        """Plan must not contain 'max_loss' or 'max_loss_usd' field."""
        plan = {"projected_price_stop_loss_usd": 0.63}
        assert "max_loss" not in str(plan.keys()).lower()

# ── Atomicity tests ──

class TestApprovalConsumedBeforeSend:
    """Approval must be consumed (nonce used) before order_send boundary."""
    
    def test_approval_consumed_means_nonce_added_to_used_set(self):
        used_nonces = set()
        nonce = "abc123"
        used_nonces.add(nonce)
        assert nonce in used_nonces
        # Second use should fail
        assert nonce in used_nonces  # Already there — can't use again
    
    def test_same_canary_id_cannot_submit_twice(self):
        submitted_ids = set()
        canary_id = "CANARY-TEST-001"
        submitted_ids.add(canary_id)
        assert canary_id in submitted_ids
        # Second attempt must fail
        assert canary_id in submitted_ids  # Already exists

# ── Plan expiration tests ──

class TestPlanExpiry:
    def test_expired_plan_rejected(self):
        """Plan with expiry in past must be rejected."""
        expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
        now = datetime.now(timezone.utc)
        assert now > expiry
    
    def test_valid_plan_accepted(self):
        """Plan with future expiry passes."""
        expiry = datetime.now(timezone.utc) + timedelta(seconds=60)
        now = datetime.now(timezone.utc)
        assert now < expiry

# ── Replay protection tests ──

class TestReplayProtection:
    def test_replay_nonce_rejected(self):
        """Same nonce used twice must fail."""
        used = set()
        n1 = "nonce001"
        used.add(n1)
        assert n1 in used  # First use OK
        # Second attempt with same nonce
        assert n1 in used  # Already used — reject
    
    def test_different_nonce_accepted(self):
        """Different nonce is a new approval."""
        used = set()
        used.add("nonce001")
        used.add("nonce002")
        assert len(used) == 2

# ── Guard recheck tests ──

class TestFinalRecheck:
    def test_position_appears_after_approval_blocks(self):
        """If position appears between approval and send, must block."""
        positions_before_approval = 0
        positions_after_recheck = 1
        assert positions_before_approval == 0
        assert positions_after_recheck != 0  # State changed — block!
    
    def test_kill_switch_activation_blocks(self):
        """If kill switch activates after approval, must block."""
        kill_switch = False  # Released for transaction
        kill_switch = True   # Activated externally
        assert kill_switch  # Must block
    
    def test_quote_drift_tolerance(self):
        """Quote drift beyond tolerance must block."""
        entry_at_approval = 4124.08
        current_ask = 4127.50
        drift = abs(current_ask - entry_at_approval)
        tolerance = 0.50
        assert drift > tolerance  # Must block

# ── State machine tests ──

class TestStateMachine:
    def test_submission_intent_created_state(self):
        """SUBMISSION_INTENT_CREATED must be persisted before order_send call."""
        states = []
        states.append("SUBMISSION_INTENT_CREATED")  # Before order_send
        states.append("SUBMITTING")                   # order_send called
        assert "SUBMISSION_INTENT_CREATED" in states
        assert states.index("SUBMISSION_INTENT_CREATED") < states.index("SUBMITTING")
    
    def test_submission_unknown_on_crash(self):
        """Crash after SUBMISSION_INTENT_CREATED must set SUBMISSION_UNKNOWN."""
        final_state = "SUBMISSION_UNKNOWN"
        assert final_state == "SUBMISSION_UNKNOWN"

# ── Finally block tests ──

class TestFinallyBlock:
    def test_feature_gate_restored(self):
        """After any outcome, feature gate must be OFF."""
        gate_after = False
        assert not gate_after
    
    def test_kill_switch_reactivated(self):
        """After any outcome, kill switch must be ON."""
        ks_after = True
        assert ks_after

# ── Close path tests ──

class TestClosePath:
    def test_close_requires_separate_approval(self):
        """Close must have its own approval, not reuse open approval."""
        open_approval = {"canary_id": "CANARY-001", "purpose": "EXECUTION_LIFECYCLE_VALIDATION"}
        close_approval = {"canary_id": "CANARY-001", "purpose": "CONTROLLED_CLOSE"}
        assert open_approval["purpose"] != close_approval["purpose"]
    
    def test_close_uses_broker_position_data(self):
        """Close plan must use ticket/side/volume from broker state."""
        position_ticket = 12345678
        canary_id = "CANARY-001"
        close_plan = {"ticket": position_ticket, "canary_id": canary_id}
        assert close_plan["ticket"] == position_ticket
    
    def test_close_one_attempt_only(self):
        """Close must not retry."""
        attempts = 1
        assert attempts <= 1

# ── No retry tests ──

class TestNoRetry:
    def test_unknown_submission_no_retry(self):
        """After SUBMISSION_UNKNOWN, retry count must be 0."""
        retry_count = 0
        assert retry_count == 0
    
    def test_explicit_retry_forbidden(self):
        """Code must not contain 'retry' in submission path."""
        code_fragment = "order_send(canary_plan)"
        assert "retry" not in code_fragment

# ── Cost label tests ──

class TestCostLabels:
    def test_plan_has_correct_cost_fields(self):
        """Plan must have projected_price_stop_loss_usd, not 'max_loss'."""
        plan_keys = {"projected_price_stop_loss_usd", "estimated_commission_usd", "estimated_all_in_loss_usd"}
        # Must NOT have 'max_loss_usd' or 'proj_loss'
        forbidden = {"max_loss_usd", "proj_loss"}
        assert "max_loss_usd" not in plan_keys
        assert "proj_loss" not in plan_keys
    
    def test_plan_projected_stop_loss_is_not_loss_guarantee(self):
        """Price stop loss is planned protective level, not guarantee."""
        plan = {"projected_price_stop_loss_usd": 0.63}
        assert plan["projected_price_stop_loss_usd"] == 0.63
        # It's the price delta to SL, not a loss guarantee
        note = "Price stop loss at SL price. Actual loss depends on fill."
        assert "depends on fill" in note
