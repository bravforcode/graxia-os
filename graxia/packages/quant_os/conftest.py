"""Pytest configuration for Quant OS tests"""
import pytest
import sys
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


@pytest.fixture
def mock_redis():
    """Mock Redis for testing"""
    class MockRedis:
        def __init__(self):
            self.store = {}
        
        def get(self, key):
            return self.store.get(key)
        
        def set(self, key, value, ex=None):
            self.store[key] = value
            return True
        
        def exists(self, key):
            return key in self.store
        
        def delete(self, key):
            if key in self.store:
                del self.store[key]
            return 1
    
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
