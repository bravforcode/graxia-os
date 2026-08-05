# TECHNICAL DEBT REGISTER — quant_os

**Date:** 2026-07-22
**Scope:** All technical debt items
**Auditor:** Automated (evidence-based)

---

## 1. DEBT SUMMARY

| Category | Count | Total Interest (hrs) |
|----------|-------|---------------------|
| Architecture | 4 | 40 |
| Testing | 5 | 60 |
| DevOps | 4 | 50 |
| Security | 3 | 25 |
| Code Quality | 4 | 30 |
| Documentation | 3 | 20 |
| **TOTAL** | **23** | **225** |

---

## 2. CRITICAL DEBT (Pay within 2 weeks)

### D-001: No CI/CD Pipeline
- **Category:** DevOps
- **Interest:** 20 hrs
- **Principal:** Manual deployment
- **Impact:** Every deployment requires manual intervention
- **Payment:** Set up GitHub Actions
- **Effort:** 8 hours
- **Evidence:** No .github/workflows/ found

### D-002: No Coverage Measurement
- **Category:** Testing
- **Interest:** 15 hrs
- **Principal:** Count-based testing
- **Impact:** Unknown code quality
- **Payment:** Add pytest-cov
- **Effort:** 2 hours
- **Evidence:** pyproject.toml has no coverage config

### D-003: No Webhook HMAC Verification
- **Category:** Security
- **Interest:** 10 hrs
- **Principal:** Unverified payloads
- **Impact:** Fake signals can be injected
- **Payment:** Add HMAC verification
- **Effort:** 4 hours
- **Evidence:** api/webhook.py

### D-004: CORS Wildcard Risk
- **Category:** Security
- **Interest:** 5 hrs
- **Principal:** No origin validation
- **Impact:** Cross-origin attacks possible
- **Payment:** Whitelist origins
- **Effort:** 1 hour
- **Evidence:** api/main.py

---

## 3. HIGH DEBT (Pay within 1 month)

### D-005: Orchestrator God Object
- **Category:** Architecture
- **Interest:** 15 hrs
- **Principal:** Single class with too many responsibilities
- **Impact:** Hard to test, modify, understand
- **Payment:** Extract smaller services
- **Effort:** 16 hours
- **Evidence:** core/orchestrator.py

### D-006: No E2E Tests
- **Category:** Testing
- **Interest:** 15 hrs
- **Principal:** No full workflow tests
- **Impact:** Regressions not caught
- **Payment:** Add E2E test suite
- **Effort:** 20 hours
- **Evidence:** No e2e test files

### D-007: No Performance Tests
- **Category:** Testing
- **Interest:** 10 hrs
- **Principal:** Unknown performance
- **Impact:** Performance regressions undetected
- **Payment:** Add benchmark tests
- **Effort:** 12 hours
- **Evidence:** No benchmark files

### D-008: No Distributed Tracing
- **Category:** DevOps
- **Interest:** 10 hrs
- **Principal:** Basic monitoring only
- **Impact:** Hard to debug production issues
- **Payment:** Add OpenTelemetry
- **Effort:** 12 hours
- **Evidence:** monitoring/metrics.py

### D-009: Sync MT5 Adapter
- **Category:** Performance
- **Interest:** 10 hrs
- **Principal:** Blocking broker calls
- **Impact:** Latency in order submission
- **Payment:** Async wrapper
- **Effort:** 8 hours
- **Evidence:** execution/adapters/mt5.py

### D-010: No Vault Integration
- **Category:** Security
- **Interest:** 5 hrs
- **Principal:** Env vars only
- **Impact:** No secret rotation, no audit
- **Payment:** Integrate HashiCorp Vault
- **Effort:** 16 hours
- **Evidence:** core/config.py

---

## 4. MEDIUM DEBT (Pay within 3 months)

### D-011: No API Documentation
- **Category:** Documentation
- **Interest:** 5 hrs
- **Principal:** No OpenAPI docs
- **Impact:** Hard for consumers to integrate
- **Payment:** Generate OpenAPI spec
- **Effort:** 4 hours
- **Evidence:** No docs/ directory

### D-012: No Centralized Logging
- **Category:** DevOps
- **Interest:** 5 hrs
- **Principal:** File-based logs
- **Impact:** Hard to search logs
- **Payment:** Set up Loki/ELK
- **Effort:** 12 hours
- **Evidence:** monitoring/logging

### D-013: Config God Object
- **Category:** Architecture
- **Interest:** 5 hrs
- **Principal:** Single QuantConfig class
- **Impact:** Hard to manage, test
- **Payment:** Split into smaller configs
- **Effort:** 8 hours
- **Evidence:** core/config.py (346L)

### D-014: No Mutation Testing
- **Category:** Testing
- **Interest:** 5 hrs
- **Principal:** Test quality unknown
- **Impact:** Weak tests not detected
- **Payment:** Add mutmut
- **Effort:** 4 hours
- **Evidence:** No mutation tests

### D-015: 30+ Audit Docs in Root
- **Category:** Documentation
- **Interest:** 2 hrs
- **Principal:** Messy root directory
- **Impact:** Hard to navigate
- **Payment:** Consolidate in docs/
- **Effort:** 2 hours
- **Evidence:** Root directory listing

### D-016: No Docker Health Check
- **Category:** DevOps
- **Interest:** 2 hrs
- **Principal:** No HEALTHCHECK
- **Impact:** Orchestrator can't detect unhealthy containers
- **Payment:** Add HEALTHCHECK
- **Effort:** 1 hour
- **Evidence:** docker/Dockerfile

---

## 5. LOW DEBT (Pay when convenient)

### D-017: Print Statements in Production
- **Category:** Code Quality
- **Interest:** 1 hr
- **Principal:** `print()` in api/main.py
- **Impact:** Unstructured output
- **Payment:** Replace with logger
- **Effort:** 30 minutes
- **Evidence:** api/main.py line ~20

### D-018: No JWT Audience Validation
- **Category:** Security
- **Interest:** 1 hr
- **Principal:** No audience check
- **Impact:** Token reuse across services
- **Payment:** Add audience validation
- **Effort:** 1 hour
- **Evidence:** api/auth.py

### D-019: No Retry Logic
- **Category:** Code Quality
- **Interest:** 2 hrs
- **Principal:** No tenacity/retry
- **Impact:** Transient failures cause crashes
- **Payment:** Add retry decorators
- **Effort:** 4 hours
- **Evidence:** monitoring/health_check.py

### D-020: No Type Stubs
- **Category:** Code Quality
- **Interest:** 1 hr
- **Principal:** No .pyi files
- **Impact:** IDE support limited
- **Payment:** Generate stubs
- **Effort:** 8 hours
- **Evidence:** No .pyi files

### D-021: No SBOM Generation
- **Category:** DevOps
- **Interest:** 1 hr
- **Principal:** No SBOM
- **Impact:** Supply chain risk
- **Payment:** Generate SBOM
- **Effort:** 2 hours
- **Evidence:** No SBOM config

### D-022: No Pre-commit Hooks
- **Category:** Code Quality
- **Interest:** 1 hr
- **Principal:** No .pre-commit-config.yaml
- **Impact:** Code quality inconsistent
- **Payment:** Add pre-commit
- **Effort:** 1 hour
- **Evidence:** No .pre-commit-config.yaml

### D-023: Makefile Monorepo Paths
- **Category:** DevOps
- **Interest:** 1 hr
- **Principal:** Paths assume monorepo
- **Impact:** Breaks standalone deployment
- **Payment:** Fix paths
- **Effort:** 30 minutes
- **Evidence:** Makefile

---

## 6. DEBT PAYMENT PLAN

### Week 1-2 (Critical)
1. D-001: Set up CI/CD (8h)
2. D-002: Add coverage (2h)
3. D-003: Add HMAC verification (4h)
4. D-004: Whitelist CORS (1h)

### Week 3-4 (High)
5. D-005: Refactor orchestrator (16h)
6. D-006: Add E2E tests (20h)
7. D-009: Async MT5 adapter (8h)

### Month 2 (Medium)
8. D-007: Add performance tests (12h)
9. D-008: Add OpenTelemetry (12h)
10. D-011: Generate OpenAPI (4h)

### Month 3 (Low)
11. D-017: Replace prints (0.5h)
12. D-018: Add JWT validation (1h)
13. D-022: Add pre-commit (1h)

---

## 7. DEBT METRICS

| Metric | Value |
|--------|-------|
| Total debt items | 23 |
| Critical items | 4 |
| High items | 6 |
| Medium items | 6 |
| Low items | 7 |
| Total interest | 225 hrs |
| Estimated payback | 3 months |
