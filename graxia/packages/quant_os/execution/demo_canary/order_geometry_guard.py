"""
Guard: verify volume and SL/TP geometry. Read-only. Fail-closed.
"""
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class GeometryGuardResult:
    passed: bool
    reason: str = ""
    volume: float = 0.0
    sl_distance_points: float = 0.0
    tp_distance_points: float = 0.0

def verify_volume(volume: float, volume_min: float, volume_max: float, volume_step: float) -> GeometryGuardResult:
    """Verify volume meets broker constraints."""
    if volume <= 0:
        return GeometryGuardResult(False, f"Volume {volume} must be positive")
    if volume < volume_min:
        return GeometryGuardResult(False, f"Volume {volume} below minimum {volume_min}")
    if volume > volume_max:
        return GeometryGuardResult(False, f"Volume {volume} above maximum {volume_max}")
    # Check step
    remainder = volume % volume_step
    if remainder > 0.0001:  # Float tolerance
        return GeometryGuardResult(False, f"Volume {volume} not multiple of step {volume_step}")
    return GeometryGuardResult(True, volume=volume)

def verify_sl_tp_geometry(
    direction: str, entry: float, sl: float, tp: float,
    point: float, stops_level: int = 0
) -> GeometryGuardResult:
    """Verify SL/TP geometry is valid for direction."""
    if direction not in ("BUY", "SELL"):
        return GeometryGuardResult(False, f"Invalid direction: {direction}")

    # SL/TP must be non-zero
    if sl == 0 or tp == 0:
        return GeometryGuardResult(False, "SL and TP must be non-zero")

    sl_distance = abs(entry - sl)
    tp_distance = abs(entry - tp)

    # Minimum distance check (stops_level in points)
    min_distance = stops_level * point
    if sl_distance < min_distance:
        return GeometryGuardResult(False, f"SL distance {sl_distance} below stops_level {min_distance}")

    if direction == "BUY":
        if sl >= entry:
            return GeometryGuardResult(False, "SL must be below entry for BUY")
        if tp <= entry:
            return GeometryGuardResult(False, "TP must be above entry for BUY")
    else:  # SELL
        if sl <= entry:
            return GeometryGuardResult(False, "SL must be above entry for SELL")
        if tp >= entry:
            return GeometryGuardResult(False, "TP must be below entry for SELL")

    return GeometryGuardResult(True, sl_distance_points=sl_distance/point if point > 0 else 0)

def verify_stops_freeze_level(stops_level: int, freeze_level: int) -> GeometryGuardResult:
    """Verify stops/freeze level constraints."""
    if stops_level < 0:
        return GeometryGuardResult(False, f"Stops level {stops_level} cannot be negative")
    if freeze_level < 0:
        return GeometryGuardResult(False, f"Freeze level {freeze_level} cannot be negative")
    return GeometryGuardResult(True)
