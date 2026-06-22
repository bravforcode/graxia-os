import pytest
from graxia.packages.quant_os.markets.eurusd.validation_protocol import (
    EURUSDValidationProtocol,
    ResearchHypothesis,
)


class TestPreconditions:
    def test_preconditions_pass_with_valid_context(self):
        proto = EURUSDValidationProtocol()
        ctx = {
            "xau_outcome": True,
            "manifest_D1": True,
            "manifest_H1": True,
            "manifest_M15": True,
            "contract_snapshot": True,
            "timezone_verified": True,
        }
        passed, issues = proto.validate_preconditions(ctx)
        assert passed is True
        assert issues == []

    def test_preconditions_fail_without_xau_outcome(self):
        proto = EURUSDValidationProtocol()
        ctx = {
            "manifest_D1": True,
            "manifest_H1": True,
            "manifest_M15": True,
            "contract_snapshot": True,
            "timezone_verified": True,
        }
        passed, issues = proto.validate_preconditions(ctx)
        assert passed is False
        assert any("PHASE_3B_OUTCOME_MISSING" in i for i in issues)

    def test_preconditions_fail_without_manifest(self):
        proto = EURUSDValidationProtocol()
        ctx = {
            "xau_outcome": True,
            "manifest_D1": True,
            "manifest_H1": True,
            # manifest_M15 missing
            "contract_snapshot": True,
            "timezone_verified": True,
        }
        passed, issues = proto.validate_preconditions(ctx)
        assert passed is False
        assert any("MANIFEST_MISSING" in i and "M15" in i for i in issues)

    def test_preconditions_fail_without_contract(self):
        proto = EURUSDValidationProtocol()
        ctx = {
            "xau_outcome": True,
            "manifest_D1": True,
            "manifest_H1": True,
            "manifest_M15": True,
            "timezone_verified": True,
        }
        passed, issues = proto.validate_preconditions(ctx)
        assert passed is False
        assert any("CONTRACT_SNAPSHOT_MISSING" in i for i in issues)


class TestHypothesis:
    def test_hypothesis_fingerprint_deterministic(self):
        h1 = ResearchHypothesis(hypothesis_id="test_001", entry_rule="rsi < 30")
        h2 = ResearchHypothesis(hypothesis_id="test_001", entry_rule="rsi < 30")
        assert h1.fingerprint() == h2.fingerprint()

    def test_hypothesis_fingerprint_differs(self):
        h1 = ResearchHypothesis(hypothesis_id="test_001", entry_rule="rsi < 30")
        h2 = ResearchHypothesis(hypothesis_id="test_002", entry_rule="rsi < 30")
        assert h1.fingerprint() != h2.fingerprint()


class TestMetrics:
    def test_validation_protocol_evaluates_metrics(self):
        proto = EURUSDValidationProtocol()
        metrics = {
            "total_trades": 50,
            "oos_trades": 20,
            "max_drawdown_pct": 12.0,
            "sharpe_ratio": 1.0,
            "profit_factor": 1.5,
        }
        passed, issues = proto.evaluate_metrics(metrics)
        assert passed is True
        assert issues == []

    def test_validation_protocol_rejects_weak_metrics(self):
        proto = EURUSDValidationProtocol()
        metrics = {
            "total_trades": 5,
            "oos_trades": 2,
            "max_drawdown_pct": 30.0,
            "sharpe_ratio": 0.1,
            "profit_factor": 0.5,
        }
        passed, issues = proto.evaluate_metrics(metrics)
        assert passed is False
        assert len(issues) >= 4
