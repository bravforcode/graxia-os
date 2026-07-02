"""Phase 7 — Canary config + demo policy tests.

RESTORED from deleted test_phase_7_canary_policy.py (BE-P9 commit 3ca14eb).
Original deleted because CanaryOrder API changed; migrated to OrderLifecycle.
"""


def test_canary_config_exists():
    from graxia.packages.quant_os.canary.config import CanaryConfig
    cfg = CanaryConfig()
    valid, issues = cfg.validate()
    assert valid, issues


def test_canary_order_exists():
    from graxia.packages.quant_os.canary.order_lifecycle import (
        OrderLifecycle, OrderState, VALID_TRANSITIONS,
    )
    assert OrderState.SIGNAL_CREATED is not None
    assert OrderLifecycle is not None
    assert len(VALID_TRANSITIONS) > 0


def test_demo_policy_default():
    from graxia.packages.quant_os.canary.demo_policy import DemoCanaryPolicy
    p = DemoCanaryPolicy()
    assert p.account_mode == "DEMO_ONLY"
    assert p.symbols == ["XAUUSD"]
    assert p.max_open_positions == 1
    assert p.auto_increase_risk is False
    assert p.auto_add_symbol is False
    assert p.auto_change_parameters is False


def test_demo_policy_validate():
    from graxia.packages.quant_os.canary.demo_policy import DemoCanaryPolicy
    valid, issues = DemoCanaryPolicy().validate()
    assert valid is True
    assert issues == []


def test_demo_policy_rejects_live():
    from graxia.packages.quant_os.canary.demo_policy import DemoCanaryPolicy
    p = DemoCanaryPolicy(account_mode="LIVE")
    valid, issues = p.validate()
    assert valid is False
    assert any("DEMO_ONLY" in i for i in issues)
