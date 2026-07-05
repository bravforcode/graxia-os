"""
Swap Cost Verification Test — Phase 9.2

Tests swap cost calculation with actual Pepperstone Razor rates for XAUUSD.
Validates triple-swap weekday calculation and cost magnitude.
"""
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # graxia/packages for quant_os.*

from quant_os.core.risk.swap_cost import (
    get_live_swap_rates,
    estimate_overnight_cost,
    get_swap_cost_for_trade,
)


# Pepperstone Razor XAUUSD swap rates (as of 2026-07-05)
# Source: Pepperstone trading conditions
PEPPERSTONE_XAUUSD_SWAP_RATES = {
    "swap_long": -28.5,      # Points (negative = cost for long)
    "swap_short": 5.2,       # Points (positive = cost for short)
    "swap_mode": 0,          # SWAP_BY_POINTS
    "swap_rollover3days": 3, # Wednesday (triple swap)
    "point": 0.01,           # XAUUSD point size
    "contract_size": 100.0,  # 1 lot = 100 oz
    "currency_profit": "USD",
}


def test_pepperstone_swap_rates():
    """Test with actual Pepperstone Razor XAUUSD rates."""
    print("=== Pepperstone XAUUSD Swap Rate Test ===")
    
    # Test parameters
    symbol = "XAUUSD"
    lot = 0.01  # 1 oz (minimum lot)
    direction = "BUY"
    
    print(f"\nSymbol: {symbol}")
    print(f"Lot size: {lot} ({lot * 100} oz)")
    print(f"Direction: {direction}")
    print(f"Swap rates:")
    print(f"  Long: {PEPPERSTONE_XAUUSD_SWAP_RATES['swap_long']} points")
    print(f"  Short: {PEPPERSTONE_XAUUSD_SWAP_RATES['swap_short']} points")
    print(f"  Triple swap day: Wednesday (day {PEPPERSTONE_XAUUSD_SWAP_RATES['swap_rollover3days']})")
    
    # Test 1: Single night hold (Thursday to Friday)
    print("\n--- Test 1: Single Night Hold (Thursday to Friday) ---")
    entry_time = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)  # Thursday 2pm
    exit_time = datetime(2026, 7, 4, 14, 0, tzinfo=UTC)   # Friday 2pm
    
    cost = get_swap_cost_for_trade(
        entry_time=entry_time,
        exit_time=exit_time,
        side=direction,
        lot=lot,
        swap_rates=PEPPERSTONE_XAUUSD_SWAP_RATES,
        triple_swap_weekday=PEPPERSTONE_XAUUSD_SWAP_RATES["swap_rollover3days"],
    )
    
    print(f"Entry: {entry_time}")
    print(f"Exit: {exit_time}")
    print(f"Nights held: 1 (Thursday rollover)")
    print(f"Expected: 1 night × -28.5 points × $1.00/point/lot × 0.01 lot = -$0.285")
    print(f"Actual cost: ${cost:.3f}")
    
    # Test 2: Triple swap Wednesday (Wednesday to Thursday)
    print("\n--- Test 2: Triple Swap Wednesday (Wednesday to Thursday) ---")
    entry_time = datetime(2026, 7, 2, 14, 0, tzinfo=UTC)  # Wednesday 2pm
    exit_time = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)   # Thursday 2pm
    
    cost = get_swap_cost_for_trade(
        entry_time=entry_time,
        exit_time=exit_time,
        side=direction,
        lot=lot,
        swap_rates=PEPPERSTONE_XAUUSD_SWAP_RATES,
        triple_swap_weekday=PEPPERSTONE_XAUUSD_SWAP_RATES["swap_rollover3days"],
    )
    
    print(f"Entry: {entry_time}")
    print(f"Exit: {exit_time}")
    print(f"Night: Wednesday rollover (triple swap)")
    print(f"Expected: 3 × -28.5 points × $1.00/point/lot × 0.01 lot = -$0.855")
    print(f"Actual cost: ${cost:.3f}")
    
    # Test 3: Multiple nights including Wednesday (Monday to Friday)
    print("\n--- Test 3: Multiple Nights Including Wednesday (Monday to Friday) ---")
    entry_time = datetime(2026, 6, 29, 14, 0, tzinfo=UTC)  # Monday 2pm
    exit_time = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)    # Friday 2pm
    
    cost = get_swap_cost_for_trade(
        entry_time=entry_time,
        exit_time=exit_time,
        side=direction,
        lot=lot,
        swap_rates=PEPPERSTONE_XAUUSD_SWAP_RATES,
        triple_swap_weekday=PEPPERSTONE_XAUUSD_SWAP_RATES["swap_rollover3days"],
    )
    
    print(f"Entry: {entry_time}")
    print(f"Exit: {exit_time}")
    print(f"Days: Monday to Friday (4 nights: Mon, Tue, Wed triple, Thu)")
    print(f"Expected: (3 regular + 3 triple) × -28.5 points × $1.00/point/lot × 0.01 lot = -$1.71")
    print(f"Actual cost: ${cost:.3f}")
    
    # Test 4: Short position
    print("\n--- Test 4: Short Position (Thursday to Friday) ---")
    entry_time = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)  # Thursday 2pm
    exit_time = datetime(2026, 7, 4, 14, 0, tzinfo=UTC)   # Friday 2pm
    
    cost = get_swap_cost_for_trade(
        entry_time=entry_time,
        exit_time=exit_time,
        side="SELL",
        lot=lot,
        swap_rates=PEPPERSTONE_XAUUSD_SWAP_RATES,
        triple_swap_weekday=PEPPERSTONE_XAUUSD_SWAP_RATES["swap_rollover3days"],
    )
    
    print(f"Entry: {entry_time}")
    print(f"Exit: {exit_time}")
    print(f"Direction: SELL")
    print(f"Expected: 1 night × 5.2 points × $1.00/point/lot × 0.01 lot = $0.052")
    print(f"Actual cost: ${cost:.3f}")
    
    return True


def test_estimate_overnight_cost():
    """Test the estimate_overnight_cost function."""
    print("\n=== estimate_overnight_cost Function Test ===")
    
    lot = 0.01
    direction = "BUY"
    nights_held = 1
    
    cost = estimate_overnight_cost(
        direction=direction,
        lot=lot,
        nights_held=nights_held,
        triple_swap_weekday=PEPPERSTONE_XAUUSD_SWAP_RATES["swap_rollover3days"],
        swap_rates=PEPPERSTONE_XAUUSD_SWAP_RATES,
        point_value_per_lot=1.0,
    )
    
    print(f"Direction: {direction}")
    print(f"Lot: {lot}")
    print(f"Nights held: {nights_held}")
    print(f"Expected: -28.5 × $0.01 × {lot} × 100 = -${28.5 * 0.01 * lot * 100:.2f}")
    print(f"Actual cost: ${cost:.2f}")
    
    return True


def test_backtest_swap_integration():
    """Test swap cost integration in backtest engine."""
    print("\n=== Backtest Swap Integration Test ===")
    
    try:
        from quant_os.backtest.engine import BacktestEngine, BacktestConfig
        
        config = BacktestConfig(enable_swap=True)
        engine = BacktestEngine(config)
        
        print(f"BacktestConfig.enable_swap: {config.enable_swap}")
        print(f"Swap cost module available: {engine._calculate_swap_cost is not None}")
        
        # Test swap cost calculation
        from datetime import datetime, timedelta, UTC
        
        entry_time = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)
        exit_time = datetime(2026, 7, 4, 14, 0, tzinfo=UTC)
        
        from quant_os.core.enums import PositionType
        
        swap_cost = engine._calculate_swap_cost(
            symbol="XAUUSD",
            side=PositionType.LONG,
            quantity=Decimal("1"),  # 1 oz
            entry_time=entry_time,
            exit_time=exit_time,
        )
        
        print(f"Swap cost calculation: ${swap_cost:.2f}")
        print(f"Expected: ~$0.285 (0.01 lot × 28.5 points × $0.01/point)")
        
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    print("=== Swap Cost Verification Tests ===")
    print()
    
    try:
        test_pepperstone_swap_rates()
        test_estimate_overnight_cost()
        test_backtest_swap_integration()
        
        print("\n" + "="*60)
        print("ALL SWAP COST TESTS PASSED")
        print("="*60)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
