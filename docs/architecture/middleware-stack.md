# Middleware Stack Architecture

**Document Version:** 1.0  
**Last Updated:** 2026-05-07  
**Status:** Production

---

## Executive Summary

Graxia OS implements a **9-layer defense-in-depth middleware stack** that provides comprehensive security controls for all HTTP requests. The middleware order is **critical** for security - incorrect ordering can break authentication, CSRF protection, or create vulnerabilities.

**Key Principle:** In FastAPI/Starlette, middleware added **LAST** executes **FIRST** (outermost layer).

---

## Middleware Stack Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    HTTP Request Arrives                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: CORS Middleware                                     │
│ • Handle preflight OPTIONS requests                          │
│ • Validate origin against whitelist                          │
│ • Add CORS headers to all responses                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Request Size Limit Middleware                       │
│ • Check Content-Length header                                │
│ • Reject requests > 10MB (configurable)                      │
│ • Prevent memory exhaustion DoS                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: IP Filter Middleware (Enterprise)                   │
│ • Check source IP against whitelist/blacklist                │
│ • Block malicious IPs at edge                                │
│ • Network-level access control                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Rate Limit Middleware                               │
│ • Track requests per IP/user (Redis-backed)                  │
│ • Enforce rate limits (100 req/min default)                  │
│ • Protect against brute force and API abuse                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Security Headers Middleware (Basic + Enterprise)    │
│ • Add CSP, HSTS, X-Frame-Options, etc.                       │
│ • Defense-in-depth browser protections                       │
│ • Prevent XSS, clickjacking, MIME sniffing                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 6: CSRF Middleware                                     │
│ • Validate CSRF tokens (double-submit cookie pattern)        │
│ • Protect state-changing operations (POST/PUT/PATCH/DELETE)  │
│ • Uses constant-time comparison (timing attack protection)   │
│ • Requires: request.state.session_id (from Layer 7)          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 7: Authentication Middleware                           │
│ • Validate JWT tokens (cookie or Authorization header)       │
│ • Establish user identity and session                        │
│ • Enforce role-based access control (RBAC)                   │
│ • Provides: request.state.session_id, authenticated_user_id  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 8: Request Sanitization Middleware                     │
│ • Detect SQL injection patterns (UNION, DROP, etc.)          │
│ • Detect XSS patterns (<script>, javascript:, etc.)          │
│ • Block malicious query params and paths                     │
│ • Last defense before application logic                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Application Logic                         │
│                  (Route Handlers, Services)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer Details

### Layer 1: CORS Middleware

**File:** `fastapi.middleware.cors.CORSMiddleware`  
**Position:** Outermost (added last)  
**Dependencies:** None

**Purpose:**
- Handle cross-origin requests from browser clients
- Validate origin against whitelist (`ALLOWED_CORS_ORIGINS`)
- Add CORS headers to all responses (including errors)
- Handle preflight OPTIONS requests

**Configuration:**
```python
ALLOWED_CORS_ORIGINS="https://app.graxia.com,https://staging.graxia.com"
```

**Security Implications:**
- **MUST be outermost** to intercept preflight OPTIONS requests
- If moved inward, CORS headers may not be added to error responses
- Prevents CSRF attacks at browser level (origin validation)

**Headers Added:**
- `Access-Control-Allow-Origin`
- `Access-Control-Allow-Credentials`
- `Access-Control-Allow-Methods`
- `Access-Control-Allow-Headers`

---

### Layer 2: Request Size Limit Middleware

**File:** `backend/app/middleware/security.py:RequestSizeLimitMiddleware`  
**Position:** Second outermost  
**Dependencies:** None

**Purpose:**
- Reject oversized requests early (default: 10MB)
- Prevent memory exhaustion DoS attacks
- Fail fast before expensive processing

**Configuration:**
```python
# Default: 10MB (10 * 1024 * 1024 bytes)
app.add_middleware(RequestSizeLimitMiddleware, max_size=10485760)
```

**Security Implications:**
- Prevents attackers from exhausting server memory
- Should be early in stack to reject before rate limiting (save resources)
- Returns 413 Payload Too Large

---

### Layer 3: IP Filter Middleware (Enterprise)

**File:** `backend/app/core/security_hardening.py:IPFilterMiddleware`  
**Position:** Third layer  
**Dependencies:** None

**Purpose:**
- Block/allow requests based on source IP address
- Support CIDR notation (e.g., `10.0.0.0/8`)
- Network-level access control

**Configuration:**
```python
# Whitelist (empty = allow all)
IP_WHITELIST="10.0.0.0/8,192.168.0.0/16,172.16.0.0/12"

# Blacklist (block specific IPs/networks)
IP_BLACKLIST="203.0.113.0/24,198.51.100.0/24"
```

**Security Implications:**
- **MUST be before rate limiting** to save resources on blocked IPs
- Whitelist mode: Only allow specified IPs (strict)
- Blacklist mode: Block specified IPs (permissive)
- Returns 403 Forbidden for blocked IPs

**IP Extraction:**
- Checks `X-Forwarded-For` header (first IP)
- Falls back to `request.client.host`

---

### Layer 4: Rate Limit Middleware

**File:** `backend/app/middleware/rate_limit.py:RateLimitMiddleware`  
**Position:** Fourth layer  
**Dependencies:** Redis (for distributed rate limiting)

**Purpose:**
- Throttle requests per IP/user
- Prevent brute force attacks on auth endpoints
- Prevent API abuse and DoS

**Configuration:**
```python
RATE_LIMIT_REQUESTS_PER_MINUTE=100  # Max requests per minute
RATE_LIMIT_BURST=10                 # Burst allowance
```

**Security Implications:**
- **MUST be before authentication** to protect auth endpoints
- Uses sliding window algorithm (Redis-backed)
- Returns 429 Too Many Requests
- Adds `X-RateLimit-*` headers to responses

**Rate Limit Headers:**
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

---

### Layer 5: Security Headers Middleware

**Files:**
- `backend/app/middleware/security.py:SecurityHeadersMiddleware` (Basic)
- `backend/app/core/security_hardening.py:SecurityHeadersMiddleware` (Enterprise)

**Position:** Fifth layer  
**Dependencies:** None

**Purpose:**
- Add security headers to all responses
- Defense-in-depth browser protections
- Prevent XSS, clickjacking, MIME sniffing, etc.

**Headers Added:**

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; ...` | Prevent XSS, data injection |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control referrer information |
| `Permissions-Policy` | `camera=(), microphone=(), ...` | Disable dangerous browser features |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | Enforce HTTPS (production only) |
| `X-DNS-Prefetch-Control` | `off` | Disable DNS prefetching |

**Security Implications:**
- Two middleware (Basic + Enterprise) for modular policies
- Order between them doesn't matter (both add headers)
- HSTS only added in production (`STRICT_BOOTSTRAP=true`)

**Configuration:**
```python
# Future: Make headers configurable per environment (see L-09)
SECURITY_HEADERS_CSP="default-src 'self'; ..."
```

---

### Layer 6: CSRF Middleware

**File:** `backend/app/middleware/security.py:CSRFMiddleware`  
**Position:** Sixth layer  
**Dependencies:** **Requires `request.state.session_id` from AuthMiddleware (Layer 7)**

**Purpose:**
- Validate CSRF tokens for state-changing operations
- Protect against cross-site request forgery attacks
- Uses double-submit cookie pattern

**Configuration:**
```python
CSRF_COOKIE_NAME="csrf_token"
CSRF_TOKEN_EXPIRY_HOURS=1  # Token expiry time
```

**Security Implications:**
- **CRITICAL: MUST be after AuthMiddleware** to access `request.state.session_id`
- If moved before Auth, all CSRF validations will fail (no session_id)
- Uses **constant-time comparison** (`hmac.compare_digest`) to prevent timing attacks
- Validates token signature and expiry timestamp

**Protected Methods:**
- POST, PUT, PATCH, DELETE (unsafe methods)

**Exempt Paths:**
- `/api/v1/auth/login`
- `/api/v1/auth/register`
- `/api/v1/integrations/alerts/telegram`
- (See `CSRF_EXEMPT_PATHS` in `backend/app/middleware/auth.py`)

**Token Format:**
```
<random_base64>.<timestamp_base64>.<signature_base64>
```

**Validation Steps:**
1. Check cookie token present (`csrf_token` cookie)
2. Check header token present (`X-CSRF-Token` header)
3. Verify tokens match (constant-time comparison)
4. Verify signature (HMAC-SHA256)
5. Verify timestamp (not expired)

---

### Layer 7: Authentication Middleware

**File:** `backend/app/middleware/auth.py:AuthMiddleware`  
**Position:** Seventh layer  
**Dependencies:** None (but provides data for CSRF layer)

**Purpose:**
- Validate JWT tokens (cookie or Authorization header)
- Establish user identity and session
- Enforce role-based access control (RBAC)
- Provide authentication context to downstream layers

**Configuration:**
```python
ACCESS_COOKIE_NAME="access_token"
ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_SIGNING_KEYS='{"v1": "your-secret-key"}'
JWT_ACTIVE_KID="v1"
```

**Security Implications:**
- **MUST be before CSRF** to provide `request.state.session_id`
- Validates JWT signature, expiry, and session activity
- Enforces role hierarchy: viewer < user < operator < admin
- Returns 401 Unauthorized for invalid tokens
- Returns 403 Forbidden for insufficient permissions

**Request State Provided:**
- `request.state.session_id` (required by CSRF layer)
- `request.state.authenticated_user_id`
- `request.state.authenticated_role`
- `request.state.auth_payload` (full JWT payload)

**Route Classification:**
- **PUBLIC:** No authentication required (e.g., `/health`, `/api/v1/auth/login`)
- **AUTHENTICATED:** Requires valid JWT (e.g., `/api/v1/opportunities`)
- **OPERATOR:** Requires operator or admin role (e.g., `/api/v1/approvals`)
- **ADMIN:** Requires admin role (e.g., `/api/v1/admin`)
- **INTERNAL:** Requires internal token or HMAC signature (e.g., webhooks)
- **BLOCKED:** Always blocked in production (e.g., `/metrics`, `/docs`)

**Internal Webhook Authentication:**
- Supports HMAC-SHA256 signature verification (preferred)
- Falls back to bearer token (deprecated)
- Validates timestamp (5-minute window) to prevent replay attacks

---

### Layer 8: Request Sanitization Middleware

**File:** `backend/app/middleware/security.py:InputSanitizationMiddleware`  
**Position:** Innermost (added first)  
**Dependencies:** None (but benefits from auth context for logging)

**Purpose:**
- Detect and block SQL injection patterns
- Detect and block XSS patterns
- Last defense before application logic

**Configuration:**
- No configuration (uses hardcoded regex patterns)

**Security Implications:**
- Innermost layer (last defense before app logic)
- Uses regex patterns (may block legitimate inputs - see M-05)
- Returns 400 Bad Request for suspicious input

**SQL Injection Patterns:**
- `UNION ... SELECT`
- `DROP ... TABLE`
- `INSERT ... INTO`
- `DELETE ... FROM`
- `--` (SQL comment)
- `#` (MySQL comment)
- `/*` (multi-line comment)

**XSS Patterns:**
- `<script>...</script>`
- `javascript:`
- `onerror=`
- `onload=`

**Limitations:**
- Regex-based (not context-aware)
- May block legitimate inputs (e.g., `--` in comments, `/*` in CSS)
- **TODO (M-05):** Implement context-aware validation

---

## Critical Ordering Rules

### Rule 1: CORS MUST be outermost

**Why:** CORS middleware must intercept all requests, including preflight OPTIONS requests, before any other processing.

**Violation Impact:**
- Preflight OPTIONS requests may be blocked by other middleware
- CORS headers may not be added to error responses
- Browser will block legitimate cross-origin requests

**Example Violation:**
```python
# ❌ WRONG: CORS not outermost
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(RateLimitMiddleware)  # Added after CORS
```

**Correct:**
```python
# ✅ CORRECT: CORS outermost (added last)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, ...)  # Added last = executes first
```

---

### Rule 2: IP Filtering MUST be before Rate Limiting

**Why:** Blocked IPs should not consume rate limit resources.

**Violation Impact:**
- Blocked IPs consume rate limit slots
- Legitimate users may be rate limited due to blocked IP traffic
- Wasted Redis operations for blocked IPs

**Example Violation:**
```python
# ❌ WRONG: Rate limiting before IP filtering
app.add_middleware(IPFilterMiddleware, ...)
app.add_middleware(RateLimitMiddleware)
```

**Correct:**
```python
# ✅ CORRECT: IP filtering before rate limiting
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IPFilterMiddleware, ...)
```

---

### Rule 3: Rate Limiting MUST be before Authentication

**Why:** Authentication endpoints must be protected from brute force attacks.

**Violation Impact:**
- Attackers can brute force authentication endpoints
- No rate limiting on login attempts
- Potential account takeover via credential stuffing

**Example Violation:**
```python
# ❌ WRONG: Auth before rate limiting
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
```

**Correct:**
```python
# ✅ CORRECT: Rate limiting before auth
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
```

---

### Rule 4: Authentication MUST be before CSRF

**Why:** CSRF middleware requires `request.state.session_id` from AuthMiddleware.

**Violation Impact:**
- **CRITICAL:** All CSRF validations will fail
- All state-changing requests (POST/PUT/PATCH/DELETE) will be blocked
- Application becomes unusable

**Example Violation:**
```python
# ❌ WRONG: CSRF before Auth
app.add_middleware(AuthMiddleware)
app.add_middleware(CSRFMiddleware)  # No session_id available!
```

**Correct:**
```python
# ✅ CORRECT: Auth before CSRF
app.add_middleware(CSRFMiddleware)  # Can access session_id
app.add_middleware(AuthMiddleware)  # Provides session_id
```

---

### Rule 5: Request Sanitization SHOULD be innermost

**Why:** Last defense before application logic, benefits from auth context.

**Violation Impact:**
- Not critical, but suboptimal
- May miss auth context for logging
- Less efficient (sanitizes before auth rejection)

**Recommendation:**
```python
# ✅ OPTIMAL: Sanitization innermost
app.add_middleware(RequestSanitizationMiddleware)  # Added first = executes last
app.add_middleware(AuthMiddleware)
# ... other middleware
```

---

## Adding New Middleware

### Decision Checklist

When adding new middleware, ask:

1. **Does it need data from other middleware?**
   - If yes, add **after** the dependency
   - Example: Audit logging needs `authenticated_user_id` → add after AuthMiddleware

2. **Should it fail fast?**
   - If yes, add closer to **outermost**
   - Example: Request validation → add early to reject invalid requests

3. **Does it modify `request.state`?**
   - Document what it provides
   - Example: AuthMiddleware provides `session_id`, `authenticated_user_id`

4. **Does it need authentication context?**
   - If yes, add **after** AuthMiddleware
   - Example: Audit logging, user-specific rate limiting

5. **Does it need to run on all requests?**
   - If yes, add **before** AuthMiddleware
   - Example: Security headers, CORS

### Example: Adding Audit Log Middleware

**Requirements:**
- Log all requests with user context
- Needs: `authenticated_user_id` (from AuthMiddleware)
- Should run on all authenticated requests

**Implementation:**
```python
# Add after AuthMiddleware, before RequestSanitization
app.add_middleware(RequestSanitizationMiddleware)
app.add_middleware(AuditLogMiddleware)  # NEW: Audit logging
app.add_middleware(AuthMiddleware)      # Provides user_id
app.add_middleware(CSRFMiddleware)
# ... rest of stack
```

**Rationale:**
- After AuthMiddleware: Can access `request.state.authenticated_user_id`
- Before RequestSanitization: Logs all requests (even sanitized ones)
- Position: Innermost layers (detailed logging)

---

## Middleware Execution Flow

### Request Flow (Inbound)

```
1. Browser sends request
   ↓
2. CORS: Validate origin, handle preflight
   ↓
3. RequestSizeLimit: Check Content-Length
   ↓
4. IPFilter: Check source IP
   ↓
5. RateLimit: Check rate limit (Redis)
   ↓
6. SecurityHeaders: (no-op on request)
   ↓
7. CSRF: Validate CSRF token (if unsafe method)
   ↓
8. Auth: Validate JWT, set request.state
   ↓
9. RequestSanitization: Check for injection patterns
   ↓
10. Application Logic: Route handler executes
```

### Response Flow (Outbound)

```
10. Application Logic: Returns response
   ↓
9. RequestSanitization: (no-op on response)
   ↓
8. Auth: (no-op on response)
   ↓
7. CSRF: (no-op on response)
   ↓
6. SecurityHeaders: Add security headers
   ↓
5. RateLimit: Add X-RateLimit-* headers
   ↓
4. IPFilter: (no-op on response)
   ↓
3. RequestSizeLimit: (no-op on response)
   ↓
2. CORS: Add CORS headers
   ↓
1. Browser receives response
```

---

## Security Testing

### Test Cases

1. **CORS Preflight:**
   ```bash
   curl -X OPTIONS http://localhost:8000/api/v1/opportunities \
     -H "Origin: https://app.graxia.com" \
     -H "Access-Control-Request-Method: POST"
   # Should return 200 with CORS headers
   ```

2. **Request Size Limit:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/opportunities \
     -H "Content-Length: 20000000" \
     -d @large-file.json
   # Should return 413 Payload Too Large
   ```

3. **IP Filtering:**
   ```bash
   # Add to .env: IP_BLACKLIST="203.0.113.0/24"
   curl -X GET http://localhost:8000/health \
     -H "X-Forwarded-For: 203.0.113.1"
   # Should return 403 Forbidden
   ```

4. **Rate Limiting:**
   ```bash
   for i in {1..150}; do
     curl -X GET http://localhost:8000/health
   done
   # Should return 429 Too Many Requests after 100 requests
   ```

5. **CSRF Protection:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/opportunities \
     -H "Authorization: Bearer <valid-token>" \
     -d '{"title": "Test"}'
   # Should return 403 CSRF token missing
   ```

6. **Authentication:**
   ```bash
   curl -X GET http://localhost:8000/api/v1/opportunities
   # Should return 401 Unauthorized
   ```

7. **Request Sanitization:**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/opportunities?q=UNION%20SELECT"
   # Should return 400 Suspicious input detected
   ```

---

## Monitoring & Observability

### Metrics to Track

1. **CORS:**
   - Preflight requests count
   - Blocked origins count

2. **Request Size Limit:**
   - Rejected requests count
   - Average request size

3. **IP Filtering:**
   - Blocked IPs count
   - Whitelist hits count

4. **Rate Limiting:**
   - Rate limit hits count
   - Top rate-limited IPs

5. **CSRF:**
   - CSRF violations count (by reason: missing, mismatch, forged)
   - Legacy token usage count

6. **Authentication:**
   - Failed auth attempts count
   - Privilege escalation attempts count

7. **Request Sanitization:**
   - Suspicious input count (by pattern: SQL, XSS)

### Logging

All middleware should log:
- **INFO:** Normal operations (e.g., "CSRF token validated")
- **WARNING:** Suspicious activity (e.g., "Rate limit exceeded")
- **ERROR:** Security violations (e.g., "CSRF token forged")
- **CRITICAL:** Privilege escalation attempts

### Audit Events

Security-critical events should be logged to audit log:
- CSRF violations
- Failed authentication attempts
- Privilege escalation attempts
- Blocked IPs
- Rate limit violations

---

## Troubleshooting

### Common Issues

#### Issue 1: CORS errors in browser

**Symptoms:**
- Browser console: "CORS policy: No 'Access-Control-Allow-Origin' header"
- Preflight OPTIONS requests fail

**Diagnosis:**
```bash
# Check CORS configuration
echo $ALLOWED_CORS_ORIGINS

# Test preflight
curl -X OPTIONS http://localhost:8000/api/v1/opportunities \
  -H "Origin: https://app.graxia.com" \
  -H "Access-Control-Request-Method: POST" \
  -v
```

**Solutions:**
1. Add origin to `ALLOWED_CORS_ORIGINS`
2. Verify CORS middleware is outermost (added last)
3. Check for middleware that blocks OPTIONS requests

---

#### Issue 2: All POST requests return 403 CSRF token missing

**Symptoms:**
- All state-changing requests fail with "CSRF token missing"
- Even with valid authentication

**Diagnosis:**
```bash
# Check if session_id is available
# Add debug logging in CSRFMiddleware:
logger.debug(f"session_id: {getattr(request.state, 'session_id', None)}")
```

**Solutions:**
1. **CRITICAL:** Verify AuthMiddleware is before CSRFMiddleware
2. Check if route is in `CSRF_EXEMPT_PATHS`
3. Verify JWT token contains `session_id` claim

---

#### Issue 3: Rate limiting not working

**Symptoms:**
- Can send unlimited requests
- No 429 responses

**Diagnosis:**
```bash
# Check Redis connection
redis-cli ping

# Check rate limit configuration
echo $RATE_LIMIT_REQUESTS_PER_MINUTE
```

**Solutions:**
1. Verify Redis is running and accessible
2. Check `REDIS_URL` configuration
3. Verify RateLimitMiddleware is added
4. Check if IP extraction is working (X-Forwarded-For)

---

#### Issue 4: Legitimate inputs blocked by sanitization

**Symptoms:**
- Valid SQL comments (`--`) in text blocked
- Valid CSS (`/*`) in styles blocked

**Diagnosis:**
```bash
# Test specific input
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Authorization: Bearer <token>" \
  -H "X-CSRF-Token: <token>" \
  -d '{"description": "This is a comment -- with dashes"}'
```

**Solutions:**
1. **Short-term:** Add input to whitelist (if possible)
2. **Long-term:** Implement context-aware validation (see M-05)
3. **Workaround:** Encode special characters in client

---

## References

- **FastAPI Middleware:** https://fastapi.tiangolo.com/advanced/middleware/
- **Starlette Middleware:** https://www.starlette.io/middleware/
- **OWASP CSRF:** https://owasp.org/www-community/attacks/csrf
- **OWASP Security Headers:** https://owasp.org/www-project-secure-headers/
- **CORS Specification:** https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS

---

## Changelog

### Version 1.0 (2026-05-07)
- Initial documentation
- Documented all 9 middleware layers
- Added critical ordering rules
- Added troubleshooting guide
- Added security testing guide

---

**Document Owner:** Security Team  
**Review Frequency:** Quarterly  
**Next Review:** 2026-08-07
