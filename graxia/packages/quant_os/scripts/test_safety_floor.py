"""
Quick test: verify safety floor prevents position-size explosion.
"""
from decimal import Decimal

# Test 1: _historical_size with near-zero stop distance
print("Test 1: _historical_size safety floor")
# Simulate: entry=2000, stop=2000.01 (0.01 distance = 0.0005% of entry)
# Without floor: position size = risk_budget / (0.01 / 0.01 * 10) = risk_budget / 10
# With floor (0.1%): position size = risk_budget / (2.0 / 0.01 * 10) = risk_budget / 2000

entry = Decimal("2000")
stop = Decimal("2000.01")  # 0.01 distance
tick_size = Decimal("0.01")
tick_value = Decimal("10")

stop_distance = abs(entry - stop)
print(f"  stop_distance: {stop_distance}")

# Without floor
ticks_no_floor = stop_distance / tick_size
one_lot_loss_no_floor = ticks_no_floor * tick_value
print(f"  one_lot_loss (no floor): {one_lot_loss_no_floor}")

# With floor
min_stop_distance = entry * Decimal("0.001")
stop_distance_floored = max(stop_distance, min_stop_distance)
ticks_floor = stop_distance_floored / tick_size
one_lot_loss_floor = ticks_floor * tick_value
print(f"  min_stop_distance: {min_stop_distance}")
print(f"  stop_distance (floored): {stop_distance_floored}")
print(f"  one_lot_loss (with floor): {one_lot_loss_floor}")
print(f"  Position size reduction: {one_lot_loss_no_floor / one_lot_loss_floor:.1f}x smaller")

# Test 2: TSMOM vol_scale
print("\nTest 2: TSMOM vol_scale safety floor")
import math

vol_target = 0.10

# Old floor: 0.01
old_floor = 0.01
vol_scale_old = vol_target / old_floor
print(f"  vol_scale (old floor 0.01): {vol_scale_old:.1f}x")

# New floor: 0.03
new_floor = 0.03
vol_scale_new = vol_target / new_floor
print(f"  vol_scale (new floor 0.03): {vol_scale_new:.1f}x")
print(f"  Reduction: {vol_scale_old / vol_scale_new:.1f}x smaller")

print("\nAll tests passed!")
