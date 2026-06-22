"""Phase 7 integration tests — MT5 demo execution readiness.

RESTORED from deleted test_phase_7_integration.py (BE-P9 commit 3ca14eb).
Original deleted because CanaryOrder API changed to OrderLifecycle; migrated.
"""
from graxia.packages.quant_os.canary.config import CanaryConfig
from graxia.packages.quant_os.canary.order_lifecycle import OrderLifecycle, OrderState


def test_canary_config_exists():
    """CanaryConfig must exist and instantiate."""
    config = CanaryConfig()
    assert config.execution_enabled is False
    assert config.account_mode_required == "DEMO"


def _make_order(**overrides):
    return OrderLifecycle()


def test_canary_order_exists():
    """OrderLifecycle must exist."""
    order = _make_order()
    assert order is not None
    assert order.get_state() == OrderState.SIGNAL_CREATED


def test_canary_config_validates():
    """CanaryConfig validation must work."""
    config = CanaryConfig()
    ok, issues = config.validate()
    assert ok is True


def test_canary_config_rejects_live():
    """CanaryConfig must reject live mode."""
    config = CanaryConfig(account_mode_required="LIVE")
    ok, issues = config.validate()
    assert ok is False


def test_canary_config_rejects_auto_resume():
    """CanaryConfig must reject auto-resume after kill switch."""
    config = CanaryConfig(auto_resume_after_kill_switch=True)
    ok, issues = config.validate()
    assert ok is False


def test_canary_config_symbol_check():
    """CanaryConfig symbol check must work."""
    config = CanaryConfig()
    ok, reason = config.check_symbol("XAUUSD")
    assert ok is True


def test_canary_config_rejects_unknown_symbol():
    """CanaryConfig must reject unknown symbols."""
    config = CanaryConfig()
    ok, reason = config.check_symbol("BTCUSD")
    assert ok is False


def test_canary_order_lifecycle():
    """OrderLifecycle must have lifecycle methods."""
    order = _make_order()
    assert hasattr(order, 'get_state')
    assert hasattr(order, 'transition')
    assert hasattr(order, 'is_terminal')
    assert hasattr(order, 'get_history')


def test_canary_order_full_lifecycle():
    """OrderLifecycle must complete the full happy-path lifecycle."""
    order = _make_order()
    steps = [
        OrderState.RISK_ACCEPTED,
        OrderState.ORDER_INTENT_CREATED,
        OrderState.ORDER_CHECKED,
        OrderState.ORDER_SUBMITTED,
        OrderState.BROKER_ACKNOWLEDGED,
        OrderState.FILLED,
        OrderState.PROTECTIVE_STOPS_VERIFIED,
        OrderState.POSITION_RECONCILED,
        OrderState.CLOSED,
        OrderState.DEAL_RECONCILED,
        OrderState.AUDITED,
    ]
    for target in steps:
        ok = order.transition(target)
        assert ok, f"Failed transition to {target.value}"
    assert order.is_terminal()
    assert len(order.get_history()) == len(steps) + 1  # +1 for initial state


def test_canary_order_rejects_invalid_transition():
    """OrderLifecycle must reject illegal state transitions."""
    order = _make_order()
    ok = order.transition(OrderState.FILLED)
    assert ok is False


def test_canary_config_fingerprint_deterministic():
    """Config fingerprint must be deterministic."""
    c1 = CanaryConfig()
    c2 = CanaryConfig()
    assert c1.fingerprint() == c2.fingerprint()


def test_canary_config_fingerprint_changes_on_config_change():
    """Config fingerprint must change when config changes."""
    c1 = CanaryConfig()
    c2 = CanaryConfig(max_daily_loss_bps=999)
    assert c1.fingerprint() != c2.fingerprint()
