"""Tests for demo canary runner."""
from graxia.packages.quant_os.canary.demo_canary_config import DemoCanaryConfig
from graxia.packages.quant_os.canary.demo_preflight import DemoPreflight
from graxia.packages.quant_os.canary.demo_order_guard import DemoOrderGuard
from graxia.packages.quant_os.canary.order_lifecycle import OrderLifecycle
from graxia.packages.quant_os.canary.demo_canary_runner import DemoCanaryRunner


def _full_context():
    return {
        "prior_phases_passed": True,
        "operator_enablement": True,
        "account_mode": "DEMO",
        "strategy_eligible": True,
        "symbol_eligible": True,
        "contract_snapshot_fresh": True,
        "market_health_green": True,
        "event_risk_clear": True,
        "kill_switch_armed": True,
    }


def test_runner_creates():
    runner = DemoCanaryRunner(
        DemoCanaryConfig(), DemoPreflight(), DemoOrderGuard(), OrderLifecycle
    )
    assert runner is not None


def test_runner_blocks_on_preflight():
    runner = DemoCanaryRunner(
        DemoCanaryConfig(), DemoPreflight(), DemoOrderGuard(), OrderLifecycle
    )
    runner.start()
    result = runner.run_cycle({"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD"}, {})
    assert result is not None
    assert result.status == "blocked"


def test_runner_completes_cycle():
    runner = DemoCanaryRunner(
        DemoCanaryConfig(), DemoPreflight(), DemoOrderGuard(), OrderLifecycle
    )
    runner.start()
    result = runner.run_cycle(
        {"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD"},
        _full_context(),
    )
    assert result is not None
    assert result.status == "completed"
    assert result.orders_filled == 1
