# DEPRECATED: This test no longer reflects canonical behavior.
# Reason: Uses risk_per_trade_pct and units_per_lot which were removed from BacktestConfig.
#         BacktestConfig now uses risk_per_trade_bps (int) with no units_per_lot field.
# Retired: Phase 3.1A.1
# Migration: Covered by test_timing.py (runs all 13 strategies including VWAPRejection).

import pytest

# ponytail: entire module retired — data format mismatch, config fields removed
pytestmark = pytest.mark.skip(reason="DEPRECATED: data format mismatch, covered by test_timing.py")


def test_deprecated_vwap():
    pass
