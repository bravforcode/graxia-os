"""Tests for BE-P8.5 Pepperstone campaign runner."""

import ast
import os
import sys
import unittest
from datetime import UTC, datetime

# Add package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestPepperstoneCampaignImports(unittest.TestCase):
    """Test that campaign runner imports correctly."""

    def test_import_runner(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import PepperstoneCampaignRunner

        self.assertTrue(callable(PepperstoneCampaignRunner))

    def test_import_helpers(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import (
            classify_session_type,
            simulate_lifecycle,
        )

        self.assertTrue(callable(classify_session_type))
        self.assertTrue(callable(simulate_lifecycle))

    def test_import_from_pipeline(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import (
            ShadowPipeline,
            validate_signal_geometry,
        )

        self.assertTrue(callable(ShadowPipeline))
        self.assertTrue(callable(validate_signal_geometry))

    def test_import_from_broker_profile(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import (
            BrokerProfile,
            validate_broker_match,
        )

        self.assertTrue(callable(BrokerProfile))
        self.assertTrue(callable(validate_broker_match))


class TestBrokerProfileValidation(unittest.TestCase):
    """Test broker profile validation logic."""

    def test_validate_matching_profile(self):
        from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

        profile = BrokerProfile()
        ok, issues = validate_broker_match(
            "Pepperstone-Demo",
            12345,
            100.0,
            2,
            0.01,
            profile,
        )
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_validate_wrong_server(self):
        from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

        profile = BrokerProfile()
        ok, issues = validate_broker_match(
            "OtherServer",
            12345,
            100.0,
            2,
            0.01,
            profile,
        )
        self.assertFalse(ok)
        self.assertTrue(any("SERVER_MISMATCH" in i for i in issues))

    def test_validate_wrong_contract_size(self):
        from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

        profile = BrokerProfile()
        ok, issues = validate_broker_match(
            "Pepperstone-Demo",
            12345,
            200.0,
            2,
            0.01,
            profile,
        )
        self.assertFalse(ok)
        self.assertTrue(any("CONTRACT_MISMATCH" in i for i in issues))

    def test_validate_wrong_digits(self):
        from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

        profile = BrokerProfile()
        ok, issues = validate_broker_match(
            "Pepperstone-Demo",
            12345,
            100.0,
            5,
            0.01,
            profile,
        )
        self.assertFalse(ok)
        self.assertTrue(any("DIGITS_MISMATCH" in i for i in issues))

    def test_validate_wrong_point(self):
        from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

        profile = BrokerProfile()
        ok, issues = validate_broker_match(
            "Pepperstone-Demo",
            12345,
            100.0,
            2,
            0.1,
            profile,
        )
        self.assertFalse(ok)
        self.assertTrue(any("POINT_MISMATCH" in i for i in issues))

    def test_profile_fingerprint_deterministic(self):
        from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile

        p1 = BrokerProfile()
        p2 = BrokerProfile()
        self.assertEqual(p1.compute_fingerprint(), p2.compute_fingerprint())


class TestNoExecutionAPIs(unittest.TestCase):
    """AST check: no order_send or execution API in module."""

    def test_no_execution_imports_in_pepperstone_campaign(self):
        module_path = os.path.join(os.path.dirname(__file__), "pepperstone_campaign.py")
        with open(module_path) as f:
            source = f.read()

        tree = ast.parse(source)

        forbidden = {"order_send", "order_check", "positions_get", "trade_open", "trade_close", "order_delete"}

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden:
                    violations.append(f"line {node.lineno}: {node.attr}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden:
                    violations.append(f"line {node.lineno}: {node.func.id}()")

        self.assertEqual(violations, [], f"Execution API references found: {violations}")

    def test_no_order_send_in_broker_observed_runner(self):
        """Also verify the existing runner remains clean."""
        module_path = os.path.join(os.path.dirname(__file__), "broker_observed_runner.py")
        with open(module_path) as f:
            source = f.read()

        tree = ast.parse(source)
        forbidden = {"order_send", "order_check"}
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden:
                    violations.append(f"line {node.lineno}: {node.attr}")

        self.assertEqual(violations, [], f"Execution API in broker_observed_runner: {violations}")


class TestSpreadTracker(unittest.TestCase):
    """Test spread percentile tracking."""

    def test_percentiles_with_data(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import SpreadTracker

        st = SpreadTracker()
        for s in range(1, 101):
            st.record(float(s))
        pcts = st.percentiles()
        self.assertAlmostEqual(pcts["p50"], 50.0, delta=1.0)
        self.assertGreater(pcts["p95"], 0.0)
        self.assertGreater(pcts["p99"], 0.0)

    def test_empty_percentiles(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import SpreadTracker

        st = SpreadTracker()
        pcts = st.percentiles()
        self.assertEqual(pcts["p50"], 0.0)


class TestLifecycleSimulator(unittest.TestCase):
    """Test hypothetical lifecycle simulation."""

    def test_sl_hit_buy(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import simulate_lifecycle

        # bid drops below SL (99.05)
        ticks = [{"bid": 99.0, "ask": 99.1}] * 5
        lc = simulate_lifecycle("BUY", 100.05, 99.05, 102.05, ticks)
        self.assertEqual(lc.exit_reason, "SL_HIT")

    def test_tp_hit_sell(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import simulate_lifecycle

        # ask drops below TP (98.05)
        ticks = [{"bid": 98.0, "ask": 98.0}] * 5
        lc = simulate_lifecycle("SELL", 100.05, 101.05, 98.05, ticks)
        self.assertEqual(lc.exit_reason, "TP_HIT")

    def test_time_stop(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import simulate_lifecycle

        # Price stays in range, should time-stop at bar 20
        ticks = [{"bid": 100.0, "ask": 100.1}] * 25
        lc = simulate_lifecycle("BUY", 100.05, 99.05, 102.05, ticks)
        self.assertEqual(lc.exit_reason, "TIME_STOP")


class TestSealedLedger(unittest.TestCase):
    """Test ledger hash chain integrity."""

    def test_verify_empty(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import SealedLedger

        ledger = SealedLedger()
        self.assertTrue(ledger.verify())

    def test_verify_after_entries(self):
        from graxia.packages.quant_os.shadow.pepperstone_campaign import SealedLedger

        ledger = SealedLedger()
        now = datetime.now(UTC).isoformat()
        ledger.append("SIG-1", "accepted", 1.5, now)
        ledger.append("SIG-2", "rejected_geometry", 0.0, now)
        ledger.append("SIG-3", "accepted", -0.3, now)
        self.assertTrue(ledger.verify())
        self.assertNotEqual(ledger.seal_hash(), "")


if __name__ == "__main__":
    unittest.main()
