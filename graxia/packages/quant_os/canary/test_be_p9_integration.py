"""Phase BE-P9 integration tests — MT5 demo canary."""
from graxia.packages.quant_os.canary.demo_canary_config import DemoCanaryConfig
from graxia.packages.quant_os.canary.order_lifecycle import OrderLifecycle, OrderState
from graxia.packages.quant_os.canary.demo_preflight import DemoPreflight
from graxia.packages.quant_os.canary.demo_order_guard import DemoOrderGuard, OrderIntent
from graxia.packages.quant_os.canary.demo_canary_runner import DemoCanaryRunner


def _full_context():
    return {
        "prior_phases_passed": True, "operator_enablement": True,
        "account_mode": "DEMO", "strategy_eligible": True,
        "symbol_eligible": True, "contract_snapshot_fresh": True,
        "market_health_green": True, "event_risk_clear": True,
        "kill_switch_armed": True,
    }


def test_config_validates():
    config = DemoCanaryConfig()
    ok, issues = config.validate()
    assert ok


def test_lifecycle_full_path():
    lc = OrderLifecycle()
    steps = [
        OrderState.RISK_ACCEPTED, OrderState.ORDER_INTENT_CREATED,
        OrderState.ORDER_CHECKED, OrderState.ORDER_SUBMITTED,
        OrderState.BROKER_ACKNOWLEDGED, OrderState.FILLED,
        OrderState.PROTECTIVE_STOPS_VERIFIED, OrderState.POSITION_RECONCILED,
        OrderState.CLOSED, OrderState.DEAL_RECONCILED, OrderState.AUDITED,
    ]
    for step in steps:
        assert lc.transition(step)
    assert lc.is_terminal()
    assert len(lc.get_history()) == 12


def test_preflight_all_pass():
    pf = DemoPreflight()
    checks = pf.check_all(_full_context())
    assert pf.all_passed()
    assert len(checks) == 9


def test_order_guard_valid():
    guard = DemoOrderGuard()
    intent = OrderIntent(
        signal_id="SIG001", symbol="XAUUSD", side="BUY",
        volume=0.01, entry_price=2350.50, stop_loss=2348.50,
        take_profit=2354.50,
    )
    ok, issues = guard.preflight(intent)
    assert ok


def test_runner_full_cycle():
    runner = DemoCanaryRunner(
        DemoCanaryConfig(), DemoPreflight(), DemoOrderGuard(), OrderLifecycle
    )
    runner.start()
    result = runner.run_cycle(
        {"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD"},
        _full_context(),
    )
    assert result.status == "completed"
    assert result.orders_filled == 1
    assert result.verdict == "SUCCESS"


def test_runner_blocks_without_context():
    runner = DemoCanaryRunner(
        DemoCanaryConfig(), DemoPreflight(), DemoOrderGuard(), OrderLifecycle
    )
    runner.start()
    result = runner.run_cycle(
        {"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD"}, {}
    )
    assert result.status == "blocked"
