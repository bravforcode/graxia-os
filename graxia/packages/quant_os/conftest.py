"""Pytest configuration for Quant OS tests"""
import pytest
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config before each test"""
    from graxia.packages.quant_os.core.config import reset_config
    reset_config()
    yield


class MockRedis:
    """In-memory Redis stand-in for tests."""

    def __init__(self):
        self.store = {}
        self._ttl = {}

    def get(self, key):
        if key in self._ttl and self._ttl[key] is not None and time.time() > self._ttl[key]:
            self.store.pop(key, None)
            self._ttl.pop(key, None)
            return None
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = str(value)
        if ex is not None:
            self._ttl[key] = time.time() + ex
        else:
            self._ttl.pop(key, None)
        return True

    def setex(self, key, time_, value):
        self.set(key, value, ex=time_)
        return True

    def ttl(self, key):
        if key not in self._ttl or self._ttl[key] is None:
            return None
        remaining = self._ttl[key] - time.time()
        if remaining <= 0:
            self.store.pop(key, None)
            self._ttl.pop(key, None)
            return None
        return remaining

    def exists(self, key):
        return self.get(key) is not None

    def delete(self, key):
        self.store.pop(key, None)
        self._ttl.pop(key, None)
        return 1


@pytest.fixture
def mock_redis():
    """Mock Redis for testing"""
    return MockRedis()


@pytest.fixture
def sample_order_data():
    """Sample order data for testing"""
    return {
        "symbol": "EURUSD",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.01,
        "strategy_id": "mtm",
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "take_profit": 1.0910,
    }
