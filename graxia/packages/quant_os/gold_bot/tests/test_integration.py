"""
Gold Bot Integration Test
"""

import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from graxia.packages.quant_os.gold_bot.core.engine import GoldBotEngine, SignalDirection, StrategySignal, AggregatedSignal
from graxia.packages.quant_os.gold_bot.core.config import BotConfig


def test_integration():
    print("=== Gold Bot Integration Test ===")
    
    # 1. Test engine initialization
    config = BotConfig(ai_validation_enabled=False)
    engine = GoldBotEngine(config)
    print("[OK] Engine initialized")
    
    # 2. Test mock data generation
    data = engine._generate_mock_data()
    assert "M15" in data
    assert len(data["M15"]["close"]) == 200
    bars = len(data["M15"]["close"])
    print(f"[OK] Mock data generated: {bars} bars per TF")
    
    # 3. Test strategy registration
    engine._register_strategies()
    strat_count = len(engine.strategies)
    assert strat_count == 13
    print(f"[OK] 13 strategies registered")
    
    # 4. Test price cache
    mid = engine.price_cache["mid"]
    assert mid > 0
    print(f"[OK] Price cache: {mid:.2f}")
    
    # 5. Test signal aggregation
    signals = [
        StrategySignal("test1", SignalDirection.BUY, 0.8, 80, 2350, 2340, 2370),
        StrategySignal("test2", SignalDirection.BUY, 0.7, 70, 2350, 2340, 2370),
        StrategySignal("test3", SignalDirection.SELL, 0.6, 60, 2350, 2360, 2330),
    ]
    
    aggregated = engine._aggregate_signals(signals)
    assert aggregated.direction == SignalDirection.BUY
    assert aggregated.total_score > 0
    assert aggregated.active_strategies == 3
    print(f"[OK] Signal aggregation: {aggregated.direction.value} score={aggregated.total_score}")
    
    # 6. Test risk bridge
    rb = engine.risk_bridge
    qty = rb._calculate_gold_position_size(10000, 2350.0, 2340.0, 0.1)
    assert qty > 0
    print(f"[OK] Position sizing: {qty:.2f} lots")
    
    # 7. Test league system
    league = engine.league
    stats = {"test": {"trades": 15, "wins": 10, "losses": 5, "pnl": 500.0,
                      "total_win_pnl": 800.0, "total_loss_pnl": 300.0,
                      "active": True, "league_tier": "A"}}
    league.update(stats)
    assert stats["test"]["league_tier"] == "S"
    tier = stats["test"]["league_tier"]
    print(f"[OK] League system: test -> Tier {tier}")
    
    # 8. Test risk check
    signal = AggregatedSignal(
        direction=SignalDirection.BUY,
        total_score=500,
        active_strategies=5,
        buy_score=500,
        sell_score=0,
        signals=[],
        consensus_entry=2350.0,
        consensus_sl=2313.0,
        consensus_tp=2424.0,
    )
    assert rb.check(signal, [], 0.0).approved == True
    print("[OK] Risk check passed")
    
    # 9. Run strategies on mock data
    async def test_strategies():
        data = engine._generate_mock_data()
        signals = await engine._run_strategies(data)
        print(f"[OK] Strategies produced {len(signals)} signals")
        for s in signals[:5]:
            print(f"     {s.strategy_name}: {s.direction.value} score={s.score}")
    
    asyncio.run(test_strategies())
    
    print()
    print("=== All Integration Tests Passed ===")


if __name__ == "__main__":
    test_integration()
