"""Hand-calculated FX cost reference case — verifies no 100x unit error.

Reference case: 1 standard lot EURUSD
- Contract size: 100,000 units
- Spread: 1.0 pip = 0.0001 EURUSD
- Commission: $7 round-trip (Pepperstone Razor)
- Slippage: 0.3 pips (30% of spread default)

Hand calculation:
- spread_cost = spread_points * contract_size * volume
             = 0.0001 * 100,000 * 1.0
             = $10.00
- slippage_cost = 0.00003 * 100,000 * 1.0
               = $3.00
- commission = $7.00 * 1.0
            = $7.00
- total = $10.00 + $3.00 + $7.00 = $20.00

If any result is 100x off, we'd see $2,000 or $0.20 instead of $20.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from execution.cost_model import BASE, STRESS_2, calculate_trade_costs


def test_eurusd_base():
    """1 standard lot EURUSD, base scenario."""
    result = calculate_trade_costs(
        entry_price=Decimal("1.0850"),
        exit_price=Decimal("1.0870"),
        volume=Decimal("1.0"),  # 1 standard lot
        contract_size=Decimal("100000"),  # EURUSD contract size
        spread_points=Decimal("0.0001"),  # 1 pip
        scenario=BASE,
        commission_per_lot=Decimal("7"),  # $7 round-trip
        slippage_points=None,  # defaults to 30% of spread
    )

    print("=== EURUSD Base Scenario (1 std lot) ===")
    print(f"  spread_cost:   ${result.spread_cost}")
    print(f"  slippage_cost: ${result.slippage_cost}")
    print(f"  commission:    ${result.commission}")
    print(f"  total_cost:    ${result.total_cost}")
    print()

    # Hand-calculated expected values
    expected_spread = Decimal("0.0001") * Decimal("100000") * Decimal("1.0")  # $10.00
    expected_slippage = Decimal("0.00003") * Decimal("100000") * Decimal("1.0")  # $3.00
    expected_commission = Decimal("7") * Decimal("1.0")  # $7.00
    expected_total = expected_spread + expected_slippage + expected_commission  # $20.00

    print(f"  Expected spread:   ${expected_spread}")
    print(f"  Expected slippage: ${expected_slippage}")
    print(f"  Expected comm:     ${expected_commission}")
    print(f"  Expected total:    ${expected_total}")
    print()

    # Check for 100x error
    tolerance = Decimal("0.01")
    if abs(result.total_cost - expected_total) > tolerance:
        print(f"  FAIL: total_cost={result.total_cost} != expected={expected_total}")
        print(f"  Difference: {abs(result.total_cost - expected_total)}")
        if result.total_cost > expected_total * 10:
            print("  POSSIBLE 100x ERROR: result is 10x+ too high")
        elif result.total_cost < expected_total / 10:
            print("  POSSIBLE 100x ERROR: result is 10x+ too low")
        return False
    else:
        print("  PASS: total_cost matches expected within $0.01")
        return True


def test_xauusd_base():
    """1 standard lot XAUUSD, base scenario."""
    result = calculate_trade_costs(
        entry_price=Decimal("3300.00"),
        exit_price=Decimal("3305.00"),
        volume=Decimal("1.0"),  # 1 standard lot
        contract_size=Decimal("100"),  # XAUUSD contract size (100 oz)
        spread_points=Decimal("0.35"),  # 3.5 pips = $0.35
        scenario=BASE,
        commission_per_lot=Decimal("0"),  # Commission embedded in spread for metals
        slippage_points=None,
    )

    print("=== XAUUSD Base Scenario (1 std lot) ===")
    print(f"  spread_cost:   ${result.spread_cost}")
    print(f"  slippage_cost: ${result.slippage_cost}")
    print(f"  commission:    ${result.commission}")
    print(f"  total_cost:    ${result.total_cost}")
    print()

    # Hand calculation:
    # spread = 0.35 * 100 * 1.0 = $35.00
    # slippage = 0.105 * 100 * 1.0 = $10.50 (30% of 0.35)
    # commission = $0
    # total = $45.50
    expected_spread = Decimal("0.35") * Decimal("100") * Decimal("1.0")
    expected_slippage = Decimal("0.105") * Decimal("100") * Decimal("1.0")
    expected_total = expected_spread + expected_slippage

    print(f"  Expected spread:   ${expected_spread}")
    print(f"  Expected slippage: ${expected_slippage}")
    print(f"  Expected total:    ${expected_total}")
    print()

    tolerance = Decimal("0.01")
    if abs(result.total_cost - expected_total) > tolerance:
        print(f"  FAIL: total_cost={result.total_cost} != expected={expected_total}")
        return False
    else:
        print("  PASS: total_cost matches expected within $0.01")
        return True


def test_eurusd_stress_2x():
    """1 standard lot EURUSD, 2x stress scenario."""
    result = calculate_trade_costs(
        entry_price=Decimal("1.0850"),
        exit_price=Decimal("1.0870"),
        volume=Decimal("1.0"),
        contract_size=Decimal("100000"),
        spread_points=Decimal("0.0001"),
        scenario=STRESS_2,
        commission_per_lot=Decimal("7"),
        slippage_points=None,
    )

    print("=== EURUSD 2x Stress Scenario ===")
    print(f"  spread_cost:   ${result.spread_cost}")
    print(f"  slippage_cost: ${result.slippage_cost}")
    print(f"  commission:    ${result.commission}")
    print(f"  total_cost:    ${result.total_cost}")
    print()

    # Under 2x stress:
    # spread = 0.0001 * 2.0 * 100000 * 1.0 = $20.00
    # slippage = 0.00003 * 2.0 * 100000 * 1.0 = $6.00
    # commission = 7 * 1.0 * 1.0 = $7.00
    # total = $33.00
    expected_spread = Decimal("0.0001") * Decimal("2.0") * Decimal("100000") * Decimal("1.0")
    expected_slippage = Decimal("0.00003") * Decimal("2.0") * Decimal("100000") * Decimal("1.0")
    expected_commission = Decimal("7") * Decimal("1.0")
    expected_total = expected_spread + expected_slippage + expected_commission

    print(f"  Expected spread:   ${expected_spread}")
    print(f"  Expected slippage: ${expected_slippage}")
    print(f"  Expected comm:     ${expected_commission}")
    print(f"  Expected total:    ${expected_total}")
    print()

    tolerance = Decimal("0.01")
    if abs(result.total_cost - expected_total) > tolerance:
        print(f"  FAIL: total_cost={result.total_cost} != expected={expected_total}")
        return False
    else:
        print("  PASS: total_cost matches expected within $0.01")
        return True


if __name__ == "__main__":
    results = []
    results.append(("EURUSD base", test_eurusd_base()))
    results.append(("XAUUSD base", test_xauusd_base()))
    results.append(("EURUSD 2x stress", test_eurusd_stress_2x()))

    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\nAll cost calculations match hand-computed reference values.")
        print("No 100x unit error detected.")
    else:
        print("\nSome calculations FAILED — possible unit error.")
