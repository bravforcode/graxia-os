# IMPLEMENTATION PLAN — quant_os

**Date:** 2026-07-22
**Scope:** Prioritized remediation plan
**Auditor:** Automated (evidence-based)

---

## 1. EXECUTIVE SUMMARY

Based on the audit findings, here is a prioritized implementation plan to bring quant_os to production readiness.

**Total Effort:** ~225 hours
**Timeline:** 3 months
**Priority:** Security → Testing → DevOps → Performance

---

## 2. PHASE 1: CRITICAL (Week 1-2)

### 2.1 Add Webhook HMAC Verification
**Priority:** CRITICAL
**Effort:** 4 hours
**Files:** api/webhook.py

**Implementation:**
```python
import hmac
import hashlib
from fastapi import Request, HTTPException

async def verify_webhook(request: Request):
    """Verify TradingView webhook HMAC signature."""
    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    secret = get_config().webhook_hmac_secret

    if not secret:
        raise HTTPException(500, "Webhook secret not configured")

    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid webhook signature")
```

**Testing:**
```python
def test_webhook_valid_signature():
    # Test with valid HMAC
    pass

def test_webhook_invalid_signature():
    # Test with invalid HMAC
    pass

def test_webhook_missing_secret():
    # Test fail-closed
    pass
```

### 2.2 Whitelist CORS Origins
**Priority:** CRITICAL
**Effort:** 1 hour
**Files:** api/main.py

**Implementation:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yourdomain.com",
        "https://admin.yourdomain.com",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 2.3 Add Coverage Measurement
**Priority:** CRITICAL
**Effort:** 2 hours
**Files:** pyproject.toml, Makefile

**Implementation:**
```toml
# pyproject.toml
[tool.coverage.run]
source = ["quant_os"]
omit = ["tests/*", "*/conftest.py"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

```makefile
# Makefile
coverage:
    python -m pytest --cov=quant_os --cov-report=html
```

### 2.4 Add Docker Health Check
**Priority:** HIGH
**Effort:** 1 hour
**Files:** docker/Dockerfile

**Implementation:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

---

## 3. PHASE 2: HIGH PRIORITY (Week 3-4)

### 3.1 Set Up CI/CD Pipeline
**Priority:** HIGH
**Effort:** 8 hours
**Files:** .github/workflows/ci.yml

**Implementation:**
```yaml
name: CI/CD Pipeline
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: make lint
      - run: make typecheck
      - run: make test
      - run: make coverage

  build:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: ./scripts/deploy_vps.sh
```

### 3.2 Implement Async MT5 Adapter
**Priority:** HIGH
**Effort:** 8 hours
**Files:** execution/adapters/mt5.py

**Implementation:**
```python
import asyncio
from functools import partial

class AsyncMT5Adapter(MT5Adapter):
    async def submit_order_async(self, order):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self.submit_order, order)
        )
```

### 3.3 Refactor Orchestrator
**Priority:** HIGH
**Effort:** 16 hours
**Files:** core/orchestrator.py

**Implementation:**
```python
# Extract into smaller services
class StrategyRunner:
    """Run strategies and collect signals."""
    pass

class OrderProcessor:
    """Process orders through risk engine."""
    pass

class PortfolioManager:
    """Manage positions and P&L."""
    pass

class TradingOrchestrator:
    """Coordinate all services."""
    def __init__(self, strategy_runner, order_processor, portfolio_manager):
        self.strategy_runner = strategy_runner
        self.order_processor = order_processor
        self.portfolio_manager = portfolio_manager
```

### 3.4 Add E2E Tests
**Priority:** HIGH
**Effort:** 20 hours
**Files:** tests/e2e/

**Implementation:**
```python
# tests/e2e/test_order_flow.py
import pytest

@pytest.mark.e2e
async def test_full_order_flow():
    """Test complete order lifecycle."""
    # 1. Send signal
    # 2. Risk check passes
    # 3. Order submitted
    # 4. Fill received
    # 5. Position updated
    pass

@pytest.mark.e2e
async def test_kill_switch():
    """Test kill switch stops all trading."""
    pass
```

---

## 4. PHASE 3: MEDIUM PRIORITY (Month 2)

### 4.1 Add Performance Tests
**Priority:** MEDIUM
**Effort:** 12 hours
**Files:** tests/performance/

**Implementation:**
```python
# tests/performance/test_latency.py
import time
import pytest

def test_order_submission_latency():
    """Measure order submission latency."""
    start = time.perf_counter()
    # Submit test order
    latency = time.perf_counter() - start
    assert latency < 0.1  # 100ms target

def test_signal_processing_throughput():
    """Measure signal processing throughput."""
    signals_per_second = process_signals_for_1_second()
    assert signals_per_second >= 1000
```

### 4.2 Add OpenTelemetry Tracing
**Priority:** MEDIUM
**Effort:** 12 hours
**Files:** api/main.py, core/orchestrator.py

**Implementation:**
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Setup
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Usage
tracer = trace.get_tracer(__name__)

async def submit_order(order):
    with tracer.start_as_current_span("submit_order"):
        # Order submission logic
        pass
```

### 4.3 Generate OpenAPI Documentation
**Priority:** MEDIUM
**Effort:** 4 hours
**Files:** docs/api/

**Implementation:**
```bash
# Generate OpenAPI spec
python -c "from api.main import app; import json; print(json.dumps(app.openapi()))" > docs/api/openapi.json
```

### 4.4 Add Vault Integration
**Priority:** MEDIUM
**Effort:** 16 hours
**Files:** core/config.py

**Implementation:**
```python
import hvac

class VaultSecrets:
    """HashiCorp Vault integration."""
    def __init__(self, vault_url, vault_token):
        self.client = hvac.Client(url=vault_url, token=vault_token)

    def get_secret(self, path, key):
        secret = self.client.secrets.kv.v2.read_secret_version(path=path)
        return secret["data"]["data"][key]
```

---

## 5. PHASE 4: LOW PRIORITY (Month 3)

### 5.1 Replace Print Statements
**Priority:** LOW
**Effort:** 0.5 hours
**Files:** api/main.py

### 5.2 Add JWT Audience Validation
**Priority:** LOW
**Effort:** 1 hour
**Files:** api/auth.py

### 5.3 Add Pre-commit Hooks
**Priority:** LOW
**Effort:** 1 hour
**Files:** .pre-commit-config.yaml

### 5.4 Consolidate Audit Docs
**Priority:** LOW
**Effort:** 2 hours
**Files:** docs/

---

## 6. IMPLEMENTATION TIMELINE

```
Week 1-2:  Phase 1 (Critical)
  - Webhook HMAC
  - CORS whitelist
  - Coverage measurement
  - Docker health check

Week 3-4:  Phase 2 (High)
  - CI/CD pipeline
  - Async MT5
  - Refactor orchestrator
  - E2E tests

Month 2:   Phase 3 (Medium)
  - Performance tests
  - OpenTelemetry
  - OpenAPI docs
  - Vault integration

Month 3:   Phase 4 (Low)
  - Code cleanup
  - Documentation
  - Pre-commit hooks
```

---

## 7. SUCCESS METRICS

| Metric | Current | Target |
|--------|---------|--------|
| Coverage | Unknown | >80% |
| CI/CD | Manual | Automated |
| E2E tests | 0 | 50+ |
| Performance tests | 0 | 20+ |
| Security tests | 0 | 30+ |
| Documentation | Partial | Complete |

---

## 8. RISK ASSESSMENT

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep | High | Stick to plan |
| Time overrun | Medium | Prioritize critical |
| Technical blockers | Medium | Research upfront |
| Resource constraints | Low | Phased approach |

---

**Plan Version:** 1.0
**Created:** 2026-07-22
**Next Review:** 2026-08-01
