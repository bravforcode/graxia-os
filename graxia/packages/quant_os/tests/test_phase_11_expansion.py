"""Phase 11 — Expansion policy + multi-broker tests."""
from graxia.packages.quant_os.governance.expansion_policy import ExpansionPolicy, ExpansionTier
from graxia.packages.quant_os.governance.multi_broker_policy import MultiBrokerPolicy, BrokerRequirements


def test_expansion_policy_default():
    p = ExpansionPolicy()
    assert p.current_tier == ExpansionTier.TIER_1
    assert p.can_add_symbol() is False
    assert p.can_increase_leverage() is False
    assert p.can_add_broker() is False


def test_expansion_policy_tier_1():
    p = ExpansionPolicy(current_tier=ExpansionTier.TIER_1)
    ok, issues = p.validate()
    assert ok is True
    assert issues == []


def test_expansion_policy_validate():
    p = ExpansionPolicy(crypto_separate_program=False)
    ok, issues = p.validate()
    assert ok is False
    assert "crypto_separate_program must be True" in issues


def test_multi_broker_policy():
    policy = MultiBrokerPolicy()
    req = BrokerRequirements()
    policy.add_broker("ibkr", req)
    assert policy.count() == 1


def test_broker_requirements_validate():
    req = BrokerRequirements()
    ok, issues = req.validate()
    assert ok is True
    assert issues == []

    req2 = BrokerRequirements(independent_contract_spec=False)
    ok2, issues2 = req2.validate()
    assert ok2 is False
    assert any("independent_contract_spec" in i for i in issues2)
