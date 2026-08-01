# DOCUMENTATION GENERATOR — quant_os

**Date:** 2026-07-22
**Scope:** Auto-generated documentation from codebase
**Auditor:** Automated (evidence-based)

---

## 1. PROJECT OVERVIEW

### What is quant_os?
quant_os is a **modular Python framework for algorithmic trading** — research, backtesting, and live execution.

### Key Features
- **Multi-strategy support** — Moving averages, RSI, Bollinger Bands, MACD, ML-based
- **4-Layer risk engine** — Per-trade → Portfolio → Account → Sizing
- **Market health gating** — Only HEALTHY state permits orders
- **Golden rules** — Immutable safety constraints
- **Multi-broker** — MT5 with failover (IC Markets, Pepperstone, XM)
- **FastAPI REST API** — Orders, positions, risk, monitoring

### Architecture
```
API (FastAPI) → Event Bus → Orchestrator → Strategies → Risk Engine → Order Manager → Broker
```

---

## 2. QUICK START

### Installation
```bash
# Clone repository
git clone <repo-url>
cd quant_os

# Install dependencies
pip install -e ".[dev]"

# Run tests
make test

# Start API
python -m api.main
```

### Configuration
```bash
# Set environment variables
export JWT_SECRET_KEY="your-secret-key"
export ADMIN_API_KEY="your-admin-key"
export MT5_LOGIN=12345678
export MT5_PASSWORD="your-password"
```

---

## 3. API REFERENCE

### Endpoints
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /health | None | Health check |
| POST | /webhook | HMAC | TradingView signal |
| GET | /orders | JWT | List orders |
| POST | /orders | JWT | Create order |
| GET | /positions | JWT | List positions |
| GET | /risk | JWT | Risk status |
| POST | /admin/kill-switch | Admin | Emergency stop |

### Authentication
```bash
# JWT token
curl -H "Authorization: Bearer <token>" /api/orders

# Admin API key
curl -H "X-Admin-Key: <key>" /api/admin/kill-switch
```

---

## 4. MODULE DOCUMENTATION

### 4.1 core/ — Business Logic

#### config.py
```python
@dataclass
class QuantConfig:
    """System configuration."""
    trading_mode: TradingMode = TradingMode.PAPER
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    # ... 346 lines
```

#### golden_rules.py
```python
@dataclass(frozen=True)
class GoldenRules:
    """Immutable safety constraints."""
    AI_CANNOT_SUBMIT_ORDER: bool = True
    HARD_STOP_DRAWDOWN_PCT: float = 15.0
    # ... 114 lines
```

#### events.py
```python
class Event: ...
class BarEvent(Event): ...
class TickEvent(Event): ...
class SignalEvent(Event): ...
class OrderEvent(Event): ...
class FillEvent(Event): ...
# ... 217 lines
```

### 4.2 risk/ — Risk Management

#### engine.py
```python
class _Layer1:
    """Per-trade validation."""
    MAX_SIGNAL_AGE_S: float = 5.0
    MIN_CONVICTION: float = 0.6

class _Layer2:
    """Portfolio validation."""
    MAX_TOTAL_EXPOSURE_PCT: float = 0.80

class _Layer3:
    """Account validation."""
    MAX_DAILY_LOSS_PCT: float = 0.02

class _Layer4:
    """Sizing optimization."""
    KELLY_CAP: float = 0.25
# ... 625 lines
```

#### risk_policy.py
```python
@dataclass(frozen=True)
class RiskPolicy:
    """Risk limits in basis points."""
    risk_per_trade_bps: int = 100  # 1.00%
    max_daily_loss_bps: int = 50   # 0.50%
    # ... 105 lines
```

### 4.3 execution/ — Order Execution

#### manager.py
```python
class OrderManager:
    """Central order management system."""
    async def submit_order(self, order: Order) -> FillEvent:
        """Submit order through risk checks to broker."""
        # ... 478 lines
```

#### order.py
```python
class OrderStateMachine:
    """Order state transitions."""
    VALID_TRANSITIONS = {
        OrderStatus.PENDING: [OrderStatus.SUBMITTED, OrderStatus.CANCELLED],
        OrderStatus.SUBMITTED: [OrderStatus.FILLED, OrderStatus.REJECTED],
        # ...
    }
```

### 4.4 market_data/ — Market Data

#### market_health.py
```python
class MarketHealthState(str, Enum):
    """Market health states."""
    HEALTHY = "HEALTHY"
    STALE_FEED = "STALE_FEED"
    WIDE_SPREAD = "WIDE_SPREAD"
    # ...

class MarketHealthMachine:
    """State machine for market health."""
    def evaluate(self) -> MarketHealthResult:
        """Evaluate all inputs, return health state."""
        # ... 284 lines
```

### 4.5 strategies/ — Trading Strategies

#### base.py
```python
class Strategy(ABC):
    """Base strategy class."""

    @abstractmethod
    def on_bar(self, bar: BarEvent) -> SignalEvent | None:
        """Process bar, return signal or None."""

    def should_long(self) -> bool:
        """Check if strategy wants to go long."""

    def should_short(self) -> bool:
        """Check if strategy wants to go short."""
    # ... 451 lines
```

### 4.6 monitoring/ — Observability

#### health_check.py
```python
def watchdog_loop(standby_webhook_url: str):
    """Run as separate process. Checks heartbeat every 300s."""
    # ... 83 lines
```

---

## 5. CONFIGURATION REFERENCE

### Environment Variables
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| JWT_SECRET_KEY | Yes | - | JWT signing secret |
| ADMIN_API_KEY | Yes | - | Admin API key |
| MT5_LOGIN | Yes | - | MT5 account number |
| MT5_PASSWORD | Yes | - | MT5 password |
| MT5_SERVER | No | Pepperstone-Demo | MT5 server |
| REDIS_URL | No | redis://localhost:6379/0 | Redis URL |
| TELEGRAM_BOT_TOKEN | No | - | Telegram bot |
| TRADING_MODE | No | PAPER | Trading mode |

### Risk Policy (risk_policy.py)
| Parameter | Default | Description |
|-----------|---------|-------------|
| risk_per_trade_bps | 100 | 1.00% per trade |
| max_daily_loss_bps | 50 | 0.50% daily |
| max_weekly_loss_bps | 150 | 1.50% weekly |
| max_total_drawdown_bps | 300 | 3.00% max drawdown |
| max_open_positions | 5 | Max positions |
| require_stop_loss | True | Must have SL |

### Golden Rules (golden_rules.py)
| Rule | Value | Description |
|------|-------|-------------|
| LIVE_TRADING_DEFAULT | False | Must enable explicitly |
| PAPER_MIN_TRADING_DAYS | 60 | Min paper trading |
| AI_CANNOT_SUBMIT_ORDER | True | AI suggests only |
| HARD_STOP_DRAWDOWN_PCT | 15.0 | Kill switch threshold |
| ORDER_EXPIRY_MICRO_SECONDS | 60 | Micro order expiry |

---

## 6. DEPLOYMENT

### Docker
```bash
# Build
docker build -t quant_os -f docker/Dockerfile .

# Run
docker run -p 8000:8000 quant_os
```

### VPS
```bash
# Deploy
./scripts/deploy_vps.sh

# Health check
curl http://localhost:8000/health
```

---

## 7. TROUBLESHOOTING

### Common Issues

#### Order Rejected
```bash
# Check risk status
curl http://localhost:8000/risk

# Check market health
curl http://localhost:8000/health
```

#### MT5 Connection Failed
```bash
# Check MT5 credentials
echo $MT5_LOGIN
echo $MT5_SERVER

# Check MT5 path
ls -la "C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
```

#### Kill Switch Triggered
```bash
# Check kill switch status
curl http://localhost:8000/risk/kill-switch

# Reset (if manual)
curl -X POST http://localhost:8000/admin/kill-switch/reset
```

---

## 8. DEVELOPMENT

### Adding a Strategy
```python
# strategies/my_strategy.py
from .base import Strategy, Signal

class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.should_long():
            return Signal(side="BUY", conviction=0.8)
        return None
```

### Adding a Broker
```python
# execution/adapters/my_broker.py
from .base import BrokerAdapter

class MyBrokerAdapter(BrokerAdapter):
    async def submit_order(self, order):
        # Implement broker API call
        pass
```

---

## 9. TESTING

### Running Tests
```bash
# Full suite
make test

# Specific test
pytest tests/test_risk_engine.py

# Coverage
make coverage
```

### Writing Tests
```python
# tests/test_my_feature.py
import pytest

def test_my_feature():
    # Arrange
    # Act
    # Assert
    assert result == expected
```

---

## 10. CHANGELOG

See CHANGELOG.md for version history.

---

**Generated:** 2026-07-22
**Version:** 0.2.0-dev
**Tests:** ~2,920
