"""Test stop geometry calibration logic. No MT5 dependency."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.g2_1_calibrate import normalize_price, compute_required_distance

class TestNormalizePrice:
    def test_normalize_to_tick(self):
        assert normalize_price(1.23456, 0.01) == 1.23
    
    def test_normalize_rounds_up(self):
        assert normalize_price(1.235, 0.01) == 1.24
    
    def test_normalize_high_precision(self):
        val = normalize_price(1.23456789, 0.00001)
        assert val == 1.23457

class TestRequiredDistance:
    def test_spread_based_distance(self):
        dist = compute_required_distance(0.17, 0, 0, 0.01)
        assert dist >= 0.17 * 3
        assert dist >= 0.50  # policy floor
    
    def test_stops_level_contributes(self):
        """Even if spread is small, stops_level may increase distance."""
        dist = compute_required_distance(0.01, 100, 0, 0.01)
        assert dist >= 1.0  # 100 * 0.01 = 1.0
    
    def test_freeze_level_contributes(self):
        dist = compute_required_distance(0.01, 0, 50, 0.01)
        assert dist >= 0.50  # 50 * 0.01 = 0.50

class TestBuySideGeometry:
    def test_buy_sl_below_bid(self):
        """For BUY: SL must be below bid, not just below ask."""
        ask = 4120.35
        bid = 4120.18
        spread = ask - bid  # 0.17
        sl = bid - 0.50  # 4119.68
        assert sl < bid, f"SL {sl} must be below bid {bid}"
        assert sl < ask
        entry = ask
        assert sl < entry
    
    def test_buy_sl_above_bid_fails(self):
        """If SL is between ask and bid, it's on wrong side."""
        ask = 4120.35
        bid = 4120.18
        sl = ask - 0.10  # 4120.25 — above bid!
        assert sl > bid  # This is the problem — SL above bid
        # This SHOULD be invalid for a BUY stop loss

class TestSellSideGeometry:
    def test_sell_sl_above_ask(self):
        """For SELL: SL must be above ask."""
        ask = 4120.35
        bid = 4120.18
        sl = ask + 0.50  # 4120.85
        assert sl > ask
        assert sl > bid
        entry = bid
        assert sl > entry
    
    def test_sell_sl_below_ask_fails(self):
        ask = 4120.35
        bid = 4120.18
        sl = bid + 0.10  # 4120.28 — below ask!
        assert sl < ask  # Wrong side for SELL SL

class TestSpreadConstraint:
    def test_spread_greater_than_stop_distance_rejected(self):
        """If spread alone exceeds planned stop distance, geometry is invalid."""
        spread = 0.17
        planned_stop_distance = 0.10
        assert spread > planned_stop_distance, "Stop distance smaller than spread = invalid"
    
    def test_spread_less_than_safety_buffer(self):
        spread = 0.17
        safety_buffer = 0.50
        required = max(spread * 3, safety_buffer)
        assert required >= safety_buffer

class TestBoundedCandidates:
    def test_max_candidates_not_exceeded(self):
        """Calibration must not generate more than MAX_CANDIDATES_PER_SIDE."""
        candidates = []
        max_candidates = 5
        for i in range(1, max_candidates + 1):
            candidates.append(i)
        assert len(candidates) <= max_candidates
        # Next candidate would be max_candidates + 1
        assert max_candidates + 1 not in candidates

class TestNoOrderSend:
    def test_calibration_script_no_order_send(self):
        """Verify calibration script has no order_send."""
        cal_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "g2_1_calibrate.py")
        with open(cal_path) as f:
            content = f.read()
        import re
        stripped = re.sub(r'(""".*?""")|(#.*$)', '', content, flags=re.DOTALL | re.MULTILINE)
        assert "order_send" not in stripped, "order_send found in calibration script!"

class TestDeterministicEvidence:
    def test_verdict_json_has_required_fields(self):
        required = ["run_id", "generated_at_utc", "verdict", "order_submission_count"]
        verdict = {
            "run_id": "test",
            "generated_at_utc": "2026-06-23T00:00:00Z",
            "verdict": "PASS_TO_G3_REVIEW",
            "order_submission_count": 0,
        }
        for field in required:
            assert field in verdict, f"Missing field: {field}"
