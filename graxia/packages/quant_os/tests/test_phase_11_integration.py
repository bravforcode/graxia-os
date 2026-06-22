"""Phase 11 integration tests — controlled expansion."""
from graxia.packages.quant_os.governance.expansion_policy import ExpansionPolicy, ExpansionTier
from graxia.packages.quant_os.governance.multi_broker_policy import MultiBrokerPolicy, BrokerRequirements


def test_expansion_policy_exists():
    """ExpansionPolicy must exist."""
    policy = ExpansionPolicy()
    assert policy.current_tier == ExpansionTier.TIER_1


def test_expansion_policy_tier_1_restrictions():
    """Tier 1 must have restrictions."""
    policy = ExpansionPolicy(current_tier=ExpansionTier.TIER_1)
    assert not policy.can_add_broker()
    assert not policy.can_increase_leverage()


def test_expansion_policy_validate():
    """ExpansionPolicy must validate."""
    policy = ExpansionPolicy()
    ok, issues = policy.validate()
    assert ok is True


def test_multi_broker_policy_works():
    """MultiBrokerPolicy must work."""
    policy = MultiBrokerPolicy()
    assert policy.count() == 0
    policy.add_broker("broker1", BrokerRequirements())
    assert policy.count() == 1


def test_broker_requirements_validate():
    """BrokerRequirements must validate."""
    req = BrokerRequirements()
    ok, issues = req.validate()
    assert ok is True


def test_broker_requirements_rejects_missing():
    """BrokerRequirements must reject missing requirements."""
    req = BrokerRequirements(independent_contract_spec=False)
    ok, issues = req.validate()
    assert ok is False
