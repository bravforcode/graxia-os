"""C0.2: prove check_data_access raises when detection is load-bearing."""

import pytest
from quant_os.core.lookahead_guard import LookaheadGuard, LookaheadViolation


def test_detection_raises_on_future_access():
    guard = LookaheadGuard(strict=True)
    guard.initialize(200)
    with pytest.raises(LookaheadViolation):
        guard.check_data_access(50, caller="test")
    assert len(guard.violations) == 1


def test_detection_allows_current_access():
    guard = LookaheadGuard(strict=True)
    guard.initialize(200)
    guard.advance()
    assert guard.check_data_access(1, caller="test") is True
    assert guard.violations == []
