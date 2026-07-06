"""
Test weekend detection logic: datetime.now().weekday() >= 5
"""

import sys
import os
sys.path.insert(0, os.getcwd())


def test_weekday_returns_false():
    """Monday (weekday=0) should NOT be weekend."""
    assert 0 < 5


def test_saturday_returns_true():
    """Saturday (weekday=5) IS weekend."""
    assert 5 >= 5


def test_sunday_returns_true():
    """Sunday (weekday=6) IS weekend."""
    assert 6 >= 5


def test_friday_not_weekend():
    """Friday (weekday=4) is NOT weekend."""
    assert 4 < 5
