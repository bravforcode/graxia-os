"""Tests for order lifecycle."""
from graxia.packages.quant_os.canary.order_lifecycle import OrderLifecycle, OrderState


def test_lifecycle_starts():
    lc = OrderLifecycle()
    assert lc.get_state() == OrderState.SIGNAL_CREATED


def test_lifecycle_valid_transitions():
    lc = OrderLifecycle()
    assert lc.transition(OrderState.RISK_ACCEPTED)
    assert lc.get_state() == OrderState.RISK_ACCEPTED
    assert lc.transition(OrderState.ORDER_INTENT_CREATED)
    assert lc.get_state() == OrderState.ORDER_INTENT_CREATED


def test_lifecycle_invalid_transition():
    lc = OrderLifecycle()
    assert not lc.transition(OrderState.FILLED)  # can't skip to FILLED


def test_lifecycle_full_path():
    lc = OrderLifecycle()
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
    for step in steps:
        assert lc.transition(step), f"Failed to transition to {step}"
    assert lc.is_terminal()
    assert len(lc.get_history()) == 12


def test_lifecycle_rejected():
    lc = OrderLifecycle()
    assert lc.transition(OrderState.REJECTED)
    assert lc.is_terminal()
