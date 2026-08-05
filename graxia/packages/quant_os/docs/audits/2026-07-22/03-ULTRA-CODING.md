# ULTRA CODING EXECUTION — quant_os

**Date:** 2026-07-22
**Scope:** Code changes based on audit findings
**Auditor:** Automated (evidence-based)

---

## 1. CRITICAL FIXES IMPLEMENTED

### 1.1 Webhook HMAC Verification
**File:** api/webhook.py
**Status:** ⚠️ REQUIRES MANUAL IMPLEMENTATION

```python
# Add to api/webhook.py

import hmac
import hashlib
from fastapi import Request, HTTPException
from ..core.config import get_config

async def verify_webhook_signature(request: Request) -> bool:
    """Verify TradingView webhook HMAC signature.

    Returns True if signature is valid, raises HTTPException otherwise.
    Fail-closed: if secret not configured, reject all.
    """
    config = get_config()
    secret = config.webhook_hmac_secret

    if not secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured"
        )

    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    if not signature:
        raise HTTPException(
            status_code=401,
            detail="Missing webhook signature"
        )

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )

    return True
```

**Usage in webhook endpoint:**
```python
@webhook_router.post("/webhook")
async def handle_webhook(request: Request):
    await verify_webhook_signature(request)
    # ... rest of handler
```

### 1.2 CORS Origin Whitelist
**File:** api/main.py
**Status:** ⚠️ REQUIRES MANUAL UPDATE

```python
# Replace in api/main.py

# Current (line ~45)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # DANGER: wildcard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Updated
ALLOWED_ORIGINS = [
    "https://yourdomain.com",
    "https://admin.yourdomain.com",
    # Add your domains here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### 1.3 Coverage Configuration
**File:** pyproject.toml
**Status:** ⚠️ REQUIRES MANUAL ADDITION

```toml
# Add to pyproject.toml

[tool.coverage.run]
source = ["quant_os"]
omit = [
    "tests/*",
    "*/conftest.py",
    "*/__pycache__/*",
]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if __name__ == .__main__.",
    "raise NotImplementedError",
]

[tool.coverage.html]
directory = "htmlcov"
```

### 1.4 Docker Health Check
**File:** docker/Dockerfile
**Status:** ⚠️ REQUIRES MANUAL ADDITION

```dockerfile
# Add to docker/Dockerfile (after EXPOSE)

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

---

## 2. HIGH PRIORITY FIXES

### 2.1 Async MT5 Adapter
**File:** execution/adapters/mt5.py
**Status:** ⚠️ REQUIRES MANUAL IMPLEMENTATION

```python
# Add to execution/adapters/mt5.py

import asyncio
from functools import partial

class AsyncMT5Adapter:
    """Async wrapper for MT5 adapter."""

    def __init__(self, sync_adapter):
        self.sync_adapter = sync_adapter

    async def submit_order_async(self, order):
        """Submit order asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self.sync_adapter.submit_order, order)
        )

    async def get_positions_async(self):
        """Get positions asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.sync_adapter.get_positions
        )
```

### 2.2 Orchestrator Refactoring
**File:** core/orchestrator.py
**Status:** ⚠️ REQUIRES MANUAL REFACTORING

```python
# Extract into smaller services

class StrategyRunner:
    """Run strategies and collect signals."""

    def __init__(self, strategies, event_bus):
        self.strategies = strategies
        self.event_bus = event_bus

    async def run_strategies(self, bar):
        signals = []
        for strategy in self.strategies:
            signal = strategy.on_bar(bar)
            if signal:
                signals.append(signal)
        return signals

class OrderProcessor:
    """Process orders through risk engine."""

    def __init__(self, risk_engine, order_manager):
        self.risk_engine = risk_engine
        self.order_manager = order_manager

    async def process_signal(self, signal):
        # Risk check
        risk_result = await self.risk_engine.evaluate(signal)
        if risk_result.rejected:
            return None

        # Submit order
        order = Order.from_signal(signal, risk_result.approved_quantity)
        return await self.order_manager.submit_order(order)

class TradingOrchestrator:
    """Coordinate all services."""

    def __init__(self, strategy_runner, order_processor, portfolio_manager):
        self.strategy_runner = strategy_runner
        self.order_processor = order_processor
        self.portfolio_manager = portfolio_manager

    async def on_bar(self, bar):
        signals = await self.strategy_runner.run_strategies(bar)
        for signal in signals:
            await self.order_processor.process_signal(signal)
```

### 2.3 JWT Audience Validation
**File:** api/auth.py
**Status:** ⚠️ REQUIRES MANUAL UPDATE

```python
# Update in api/auth.py

def decode_token(token: str) -> dict:
    """Decode and verify JWT token."""
    config = get_config()
    secret = config.jwt_secret_key

    if not secret:
        raise RuntimeError("JWT_SECRET_KEY not configured")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="quant_os",  # Add audience validation
            issuer="quant_os",   # Add issuer validation
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
```

---

## 3. TESTING IMPLEMENTATION

### 3.1 Webhook Tests
**File:** tests/test_webhook.py
**Status:** ⚠️ REQUIRES MANUAL CREATION

```python
import pytest
from fastapi.testclient import TestClient
import hmac
import hashlib

def test_webhook_valid_signature(client, webhook_secret):
    """Test webhook with valid HMAC signature."""
    payload = b'{"action":"buy","symbol":"EURUSD"}'
    signature = hmac.new(
        webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    response = client.post(
        "/webhook",
        content=payload,
        headers={"X-Signature": signature}
    )
    assert response.status_code == 200

def test_webhook_invalid_signature(client):
    """Test webhook with invalid signature."""
    response = client.post(
        "/webhook",
        content=b'{"action":"buy"}',
        headers={"X-Signature": "invalid"}
    )
    assert response.status_code == 401

def test_webhook_missing_signature(client):
    """Test webhook without signature."""
    response = client.post(
        "/webhook",
        content=b'{"action":"buy"}'
    )
    assert response.status_code == 401
```

### 3.2 Coverage Baseline
**File:** Makefile
**Status:** ⚠️ REQUIRES MANUAL UPDATE

```makefile
# Add to Makefile

coverage:
    python -m pytest --cov=quant_os --cov-report=html --cov-report=term

coverage-check:
    python -m pytest --cov=quant_os --cov-fail-under=80
```

---

## 4. IMPLEMENTATION CHECKLIST

- [ ] 1.1 Add webhook HMAC verification
- [ ] 1.2 Update CORS origins
- [ ] 1.3 Add coverage configuration
- [ ] 1.4 Add Docker health check
- [ ] 2.1 Implement async MT5 adapter
- [ ] 2.2 Refactor orchestrator
- [ ] 2.3 Add JWT audience validation
- [ ] 3.1 Add webhook tests
- [ ] 3.2 Add coverage baseline

---

## 5. VERIFICATION

After implementing changes, run:
```bash
# Run tests
make test

# Check coverage
make coverage

# Type check
make typecheck

# Lint
make lint
```

---

**Note:** These changes require manual implementation. The code snippets above are ready-to-use templates.
