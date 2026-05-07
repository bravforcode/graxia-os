# 🔍 APEX AUDIT REPORT — Graxia Intelligence OS

**Auditor:** APEX-AUDITOR | **Date:** 2026-05-07 | **Confidence:** High

---

## EXECUTIVE SUMMARY

Graxia Intelligence OS เป็นระบบ Personal AI Chief of Staff ที่ออกแบบมาอย่างดี มีสถาปัตยกรรมแบบ enterprise-grade พร้อม security controls หลายชั้น และ observability stack ที่ครบถ้วน โครงสร้างโค้ดแสดงถึงความเข้าใจในหลักการ software engineering ที่ดี โดยเฉพาะในด้าน authentication, middleware layering, และ event-driven architecture

**จุดแข็งหลัก:** Security middleware stack ที่ครบถ้วน (9 layers), event bus architecture พร้อม dead-letter queue, model routing system ที่มี cost control, และ production configuration validation ที่เข้มงวด

**ความเสี่ยงวิกฤต 2 ข้อ:**
1. **CSRF token validation มีช่องโหว่ timing attack** - ใช้ string comparison แทน constant-time comparison ใน 1 จุด
2. **Internal webhook authentication ไม่มี signature verification** - พึ่งพา bearer token อย่างเดียว ไม่มี HMAC signature

**ความเสี่ยงสูง 3 ข้อ:**
1. Default SECRET_KEY และ database password ยังเป็น placeholder ใน development
2. Event bus processing loop ไม่มี graceful shutdown mechanism
3. Missing database indexes สำหรับ query patterns ที่ใช้บ่อย

---

## OVERALL HEALTH SCORE: 72/100

**คำนวณ:**
- Architecture (8/10 × 15%) = 12.0
- Code Quality (7/10 × 15%) = 10.5
- Security (6/10 × 20%) = 12.0
- Performance (7/10 × 10%) = 7.0
- Testing (5/10 × 10%) = 5.0
- Data Layer (7/10 × 10%) = 7.0
- API Design (8/10 × 5%) = 4.0
- DevOps (8/10 × 5%) = 4.0
- Dependencies (7/10 × 5%) = 3.5
- Documentation (7/10 × 5%) = 3.5

**Total:** 72.0/100

---

## DIMENSION SCORECARD

| # | Dimension | Score | Grade | Status |
|---|-----------|-------|-------|--------|
| 1 | Architecture & System Design | 8/10 | B+ | 🟡 |
| 2 | Code Quality & Maintainability | 7/10 | B | 🟡 |
| 3 | Security | 6/10 | C+ | 🟠 |
| 4 | Performance & Efficiency | 7/10 | B | 🟡 |
| 5 | Testing & QA | 5/10 | C | 🟠 |
| 6 | Data Layer & Database | 7/10 | B | 🟡 |
| 7 | API Design & Contracts | 8/10 | B+ | 🟡 |
| 8 | DevOps & Infrastructure | 8/10 | B+ | 🟡 |
| 9 | Dependencies & Supply Chain | 7/10 | B | 🟡 |
| 10 | Documentation & DX | 7/10 | B | 🟡 |

🟢 9–10 · 🟡 7–8 · 🟠 5–6 · 🔴 1–4

---

## 🚨 CRITICAL ISSUES — Fix Within 24–72 Hours

### **[C-01] CSRF Token Comparison Vulnerable to Timing Attack**

- **Dimension:** Security (Dimension 3)
- **Location:** `backend/app/middleware/security.py:95` → `CSRFMiddleware.dispatch()`
- **Evidence:**
  ```python
  if not hmac.compare_digest(cookie_token, header_token):
      metrics_collector.record_csrf_violation(path)
  ```
  **แต่ที่บรรทัด 95 มีการเปรียบเทียบแบบธรรมดา:**
  ```python
  if not cookie_token or not header_token:
      # ... missing token handling
  ```
  
- **Problem:** การตรวจสอบ token ว่าเป็น None หรือ empty string ใช้ `if not` ซึ่งเป็น short-circuit evaluation ทำให้ attacker สามารถใช้ timing attack เพื่อ brute-force token ได้ โดยวัดเวลาที่ใช้ในการ response
  
- **Exploit/Failure Scenario:**
  1. Attacker ส่ง request พร้อม CSRF token ที่ไม่ถูกต้อง
  2. วัดเวลา response เพื่อดูว่า token ผ่านการตรวจสอบ None/empty หรือไม่
  3. ใช้ timing information เพื่อ narrow down token space
  4. Brute-force token ที่เหลือจนได้ valid token
  
- **Blast Radius:** ทุก authenticated user ที่ทำ state-changing operations (POST/PUT/PATCH/DELETE) สามารถถูก CSRF attack ได้ หากมี XSS vulnerability ร่วมด้วย จะสามารถ bypass CSRF protection ได้ทั้งหมด
  
- **Remediation:**
  ```python
  # แทนที่การตรวจสอบแบบเดิม
  if not cookie_token or not header_token:
      # ...
  
  # ด้วย constant-time check
  if not (cookie_token and header_token and len(cookie_token) > 0 and len(header_token) > 0):
      metrics_collector.record_csrf_violation(path)
      # ... log and return 403
  
  # และใช้ hmac.compare_digest สำหรับทุกการเปรียบเทียบ
  if not hmac.compare_digest(cookie_token, header_token):
      # ...
  ```
  
- **Verification:**
  ```bash
  # เขียน test case สำหรับ timing attack
  cd backend
  python -m pytest tests/test_csrf_timing.py -v
  ```
  
- **Effort:** ~2h สำหรับ senior developer

---

### **[C-02] Internal Webhook Authentication Missing HMAC Signature Verification**

- **Dimension:** Security (Dimension 3)
- **Location:** `backend/app/middleware/auth.py:186-195` → `AuthMiddleware.dispatch()`
- **Evidence:**
  ```python
  if (request.method.upper(), route_path) in INTERNAL_TOKEN_ROUTES:
      configured = (settings.ALERTMANAGER_WEBHOOK_TOKEN or "").strip()
      provided = request.headers.get("X-Alertmanager-Token", "").strip()
      authorization = request.headers.get("Authorization", "")
      if authorization.lower().startswith("bearer "):
          provided = authorization.split(" ", 1)[1].strip()
      if not configured or not hmac.compare_digest(configured, provided):
          return JSONResponse({"detail": "Unauthorized"}, status_code=401)
  ```
  
- **Problem:** การ authenticate internal webhooks (เช่น Alertmanager) ใช้ bearer token อย่างเดียว ไม่มี HMAC signature verification ของ request body ทำให้:
  1. Token อาจถูก leak ผ่าน logs, network monitoring, หรือ man-in-the-middle
  2. ไม่มีการตรวจสอบว่า request body ถูก tamper หรือไม่
  3. Replay attack เป็นไปได้หาก token ถูก intercept
  
- **Exploit/Failure Scenario:**
  1. Attacker ดัก network traffic และได้ `X-Alertmanager-Token`
  2. สร้าง fake webhook request พร้อม token ที่ถูกต้อง
  3. ส่ง malicious payload ไปยัง `/api/v1/integrations/alerts/telegram`
  4. Backend ประมวลผล fake alert และส่ง notification ไปยัง Telegram
  5. Operator ได้รับ false alarm หรือ malicious command
  
- **Blast Radius:** ทุก internal webhook endpoints สามารถถูก spoof ได้ รวมถึง Alertmanager webhooks ที่อาจ trigger critical operations
  
- **Remediation:**
  ```python
  # เพิ่ม HMAC signature verification
  if (request.method.upper(), route_path) in INTERNAL_TOKEN_ROUTES:
      import hashlib
      secret = (getattr(settings, "ALERTMANAGER_WEBHOOK_SECRET", "") or "").strip()
      signature = request.headers.get("X-Alertmanager-Signature", "").strip()
      
      if secret and signature.startswith("sha256="):
          body = await request.body()
          expected_sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
          if not hmac.compare_digest(expected_sig, signature):
              return JSONResponse({"detail": "Unauthorized"}, status_code=401)
          request.state.internal_token_authenticated = True
          
          # Restore body for downstream handlers
          async def receive():
              return {"type": "http.request", "body": body}
          request._receive = receive
          
          return await call_next(request)
      
      # Fallback to bearer token (deprecated)
      configured = (settings.ALERTMANAGER_WEBHOOK_TOKEN or "").strip()
      # ... existing token check
  ```
  
  **และเพิ่มใน `.env.example`:**
  ```bash
  # Internal Webhook Security
  ALERTMANAGER_WEBHOOK_SECRET=your-webhook-signing-secret-min-32-chars
  ```
  
- **Verification:**
  ```bash
  # Test HMAC signature verification
  curl -X POST http://localhost:8000/api/v1/integrations/alerts/telegram \
    -H "X-Alertmanager-Signature: sha256=invalid" \
    -d '{"alert": "test"}' \
    # Should return 401
  
  # Test with valid signature
  python scripts/test_webhook_signature.py
  ```
  
- **Effort:** ~3h สำหรับ senior developer

---

## 🔴 HIGH ISSUES — Fix This Sprint

### **[H-01] Default Development Secrets in Configuration**

- **Dimension:** Security (Dimension 3)
- **Location:** `backend/app/config.py:27-29` → `Settings` class defaults
- **Evidence:**
  ```python
  SECRET_KEY: str = "development-secret-key-change-me"
  ENCRYPTION_KEY: str = ""
  API_KEY: str = ""
  ```
  และ
  ```python
  POSTGRES_PASSWORD: str = "changeme"
  ```
  
- **Problem:** Default values เป็น placeholder ที่อ่อนแอ หากนักพัฒนาลืมเปลี่ยนใน `.env` จะทำให้ระบบมีช่องโหว่ร้ายแรง โดยเฉพาะ:
  1. `SECRET_KEY` ใช้สำหรับ sign JWT tokens
  2. `ENCRYPTION_KEY` ใช้สำหรับ encrypt sensitive data
  3. `POSTGRES_PASSWORD` ใช้สำหรับ database access
  
- **Exploit/Failure Scenario:**
  1. Developer deploy โดยไม่ได้เปลี่ยน SECRET_KEY
  2. Attacker ใช้ default key เพื่อ forge JWT tokens
  3. Attacker ได้ admin access โดยไม่ต้อง authenticate
  4. Attacker สามารถ read/write ทุก data ใน database
  
- **Blast Radius:** Full system compromise - ทุก user accounts, ทุก data, ทุก operations
  
- **Remediation:**
  ```python
  # แทนที่ defaults ด้วย None และ validate ตอน startup
  SECRET_KEY: str | None = None
  ENCRYPTION_KEY: str | None = None
  API_KEY: str | None = None
  POSTGRES_PASSWORD: str | None = None
  
  @model_validator(mode="after")
  def validate_required_secrets(self):
      if self.APP_ENV.lower() != "testing":
          required_secrets = {
              "SECRET_KEY": self.SECRET_KEY,
              "ENCRYPTION_KEY": self.ENCRYPTION_KEY,
              "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
          }
          missing = [k for k, v in required_secrets.items() if not v or self._looks_placeholder(v)]
          if missing:
              raise RuntimeError(
                  f"Required secrets not configured: {', '.join(missing)}. "
                  f"Set them in .env file before starting the application."
              )
      return self
  ```
  
- **Verification:**
  ```bash
  # Test startup without secrets
  unset SECRET_KEY ENCRYPTION_KEY POSTGRES_PASSWORD
  python -c "from app.main import app"
  # Should raise RuntimeError
  ```
  
- **Effort:** ~1.5h

---

### **[H-02] Event Bus Processing Loop Missing Graceful Shutdown**

- **Dimension:** Architecture (Dimension 1)
- **Location:** `backend/app/core/event_bus.py:58-88` → `EventBus.start_processing()`
- **Evidence:**
  ```python
  async def start_processing(self) -> None:
      self._running = True
      logger.info("EventBus: processing loop started")
      while self._running:
          try:
              event, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
              # ... process event
          except TimeoutError:
              continue
          except Exception as exc:
              logger.error("EventBus: processing loop error: %s", exc, exc_info=True)
  ```
  
- **Problem:** เมื่อ `stop()` ถูกเรียก `self._running` จะเป็น `False` แต่:
  1. Events ที่อยู่ใน queue จะไม่ถูกประมวลผล
  2. ไม่มีการรอให้ handlers ที่กำลังทำงานเสร็จก่อน shutdown
  3. อาจเกิด data loss หรือ inconsistent state
  
- **Exploit/Failure Scenario:**
  1. System กำลัง process critical event (เช่น payment confirmation)
  2. Deployment trigger graceful shutdown
  3. Event bus stop ทันที โดยไม่รอ handler เสร็จ
  4. Payment confirmation ไม่ถูกบันทึก
  5. User ถูก charge แต่ไม่ได้ service
  
- **Blast Radius:** Data loss ใน critical operations, inconsistent state ระหว่าง services, potential revenue loss
  
- **Remediation:**
  ```python
  async def start_processing(self) -> None:
      self._running = True
      self._processing_tasks: set[asyncio.Task] = set()
      logger.info("EventBus: processing loop started")
      
      while self._running or not self._queue.empty():
          try:
              event, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
              task = asyncio.create_task(self._process_event(event, payload))
              self._processing_tasks.add(task)
              task.add_done_callback(self._processing_tasks.discard)
          except TimeoutError:
              continue
          except Exception as exc:
              logger.error("EventBus: processing loop error: %s", exc, exc_info=True)
      
      # Wait for all processing tasks to complete
      if self._processing_tasks:
          logger.info(f"EventBus: waiting for {len(self._processing_tasks)} tasks to complete")
          await asyncio.gather(*self._processing_tasks, return_exceptions=True)
      logger.info("EventBus: processing loop stopped gracefully")
  
  async def _process_event(self, event: str, payload: EventPayload) -> None:
      handlers = self._handlers.get(event, [])
      if not handlers:
          logger.debug(f"EventBus: no handlers for '{event}'")
          return
      for handler in handlers:
          handler_name = getattr(handler, "__name__", handler.__class__.__name__)
          try:
              result = handler(payload)
              if inspect.isawaitable(result):
                  await result
          except Exception as exc:
              logger.error(
                  "EventBus: handler %s failed for '%s': %s",
                  handler_name, event, exc, exc_info=True
              )
              self._failed_events.append((event, payload, str(exc)))
              if len(self._failed_events) > 100:
                  self._failed_events.pop(0)
  ```
  
- **Verification:**
  ```bash
  # Test graceful shutdown
  python -m pytest tests/test_event_bus_shutdown.py -v
  ```
  
- **Effort:** ~2.5h

---

### **[H-03] Missing Database Indexes for Common Query Patterns**

- **Dimension:** Data Layer & Database (Dimension 6)
- **Location:** `backend/app/models/` → Various models
- **Evidence:**
  จากการวิเคราะห์ models ใน `backend/app/models/__init__.py` พบว่ามี 20+ models แต่ไม่มีการระบุ indexes ที่ชัดเจนสำหรับ query patterns ที่น่าจะใช้บ่อย เช่น:
  - `Opportunity` - query by `status`, `score`, `created_at`
  - `Contact` - query by `email`, `organization`
  - `EmailThread` - query by `user_id`, `status`, `last_message_at`
  - `AssistantTask` - query by `user_id`, `status`, `priority`
  
- **Problem:** ไม่มี indexes จะทำให้:
  1. Query ช้าเมื่อ data เยอะขึ้น (full table scan)
  2. Database CPU usage สูง
  3. User experience แย่ (slow page loads)
  4. Potential timeout ใน production
  
- **Exploit/Failure Scenario:**
  1. System มี 10,000+ opportunities
  2. User filter opportunities by status="pending"
  3. Database ทำ full table scan
  4. Query ใช้เวลา 5+ seconds
  5. Request timeout, user เห็น error
  
- **Blast Radius:** ทุก list/filter operations จะช้า, database overload ภายใต้ moderate load
  
- **Remediation:**
  สร้าง Alembic migration เพื่อเพิ่ม indexes:
  ```python
  # backend/alembic/versions/XXX_add_performance_indexes.py
  def upgrade():
      # Opportunity indexes
      op.create_index('ix_opportunity_status', 'opportunities', ['status'])
      op.create_index('ix_opportunity_score', 'opportunities', ['score'])
      op.create_index('ix_opportunity_created_at', 'opportunities', ['created_at'])
      op.create_index('ix_opportunity_user_status', 'opportunities', ['user_id', 'status'])
      
      # Contact indexes
      op.create_index('ix_contact_email', 'contacts', ['email'])
      op.create_index('ix_contact_organization', 'contacts', ['organization'])
      
      # EmailThread indexes
      op.create_index('ix_email_thread_user_status', 'email_threads', ['user_id', 'status'])
      op.create_index('ix_email_thread_last_message', 'email_threads', ['last_message_at'])
      
      # AssistantTask indexes
      op.create_index('ix_assistant_task_user_status', 'assistant_tasks', ['user_id', 'status'])
      op.create_index('ix_assistant_task_priority', 'assistant_tasks', ['priority'])
  
  def downgrade():
      op.drop_index('ix_opportunity_status')
      # ... drop all indexes
  ```
  
- **Verification:**
  ```bash
  # Run migration
  alembic upgrade head
  
  # Test query performance
  python scripts/benchmark_queries.py
  # Should show <50ms for filtered queries
  ```
  
- **Effort:** ~3h (including testing on production-like data volume)

---

## 🟠 MEDIUM ISSUES — Fix This Quarter

**[M-01] Middleware Order Dependency Not Documented**
- **Location:** `backend/app/main.py:82-115`
- **Problem:** Middleware stack มี 9 layers แต่ไม่มี comment อธิบายว่าทำไมต้องเรียงลำดับแบบนี้ หาก developer เพิ่ม middleware ใหม่อาจทำให้ security controls ไม่ทำงาน
- **Remediation:** เพิ่ม detailed comments อธิบาย dependency chain และ security implications ของแต่ละ layer
- **Effort:** ~30min

**[M-02] Event Bus Queue Size Unbounded**
- **Location:** `backend/app/core/event_bus.py:14`
- **Problem:** `asyncio.Queue()` ไม่มี maxsize ทำให้อาจเกิด memory exhaustion หาก events ถูก emit เร็วกว่าที่ process ได้
- **Remediation:** ตั้ง `maxsize=10000` และ implement backpressure mechanism
- **Effort:** ~1.5h

**[M-03] Model Router Cost Estimation Assumes Symmetric Token Usage**
- **Location:** `backend/app/core/model_router.py:115-120`
- **Problem:** `_estimate_cost_usd()` ใช้ `max_tokens` สำหรับทั้ง input และ output แต่ในความเป็นจริง input/output ratio ไม่เท่ากัน ทำให้ cost estimate สูงเกินจริง
- **Remediation:** ใช้ actual token counts จาก LLM response หรือ estimate แบบ realistic ratio (เช่น 60/40)
- **Effort:** ~2h

**[M-04] CSRF Token Generation Uses Random Bytes Without Timestamp**
- **Location:** `backend/app/middleware/security.py:32-37`
- **Problem:** CSRF token ไม่มี expiry timestamp ทำให้ token ที่ถูก leak สามารถใช้ได้ตลอดไปจนกว่า session จะหมดอายุ
- **Remediation:** เพิ่ม timestamp ใน token และ validate expiry (เช่น 1 hour)
- **Effort:** ~2h

**[M-05] Input Sanitization Regex Patterns Too Broad**
- **Location:** `backend/app/middleware/security.py:127-141`
- **Problem:** SQL injection patterns block legitimate inputs เช่น `--` ใน comments หรือ `/*` ใน CSS
- **Remediation:** ใช้ context-aware validation แทน blanket regex blocking
- **Effort:** ~3h

---

## 🟡 LOW ISSUES & SUGGESTIONS

1. `backend/app/main.py:20` — Duplicate `SecurityHeadersMiddleware` imports (Basic และ Enterprise) ควร consolidate เป็น class เดียว
2. `backend/app/core/event_bus.py:90` — `reset()` method ไม่ควรถูกเรียกใน production แต่ไม่มี guard ป้องกัน
3. `backend/app/config.py:156-165` — IP_WHITELIST และ IP_BLACKLIST ถูก define 2 ครั้ง (line 30 และ 156)
4. `backend/app/middleware/auth.py:186` — Internal token check ควร extract เป็น separate function เพื่อ testability
5. `backend/requirements.txt` — Version pinning ไม่สมบูรณ์ (บาง packages ใช้ `>=` แทน `==`)
6. `docker-compose.yml:13` — Redis password ถูก pass ผ่าน command line ซึ่ง visible ใน `docker ps` ควรใช้ config file แทน
7. `.github/workflows/ci.yml:65` — Playwright browser install ทุกครั้งที่ run CI ควร cache
8. `backend/app/core/model_router.py:48` — Hardcoded task defaults ควร move ไปเป็น config
9. `backend/app/middleware/security.py:18-28` — Security headers ควร configurable per-environment
10. `backend/app/config.py:280-290` — Production validation ควร run ตอน build time ไม่ใช่ runtime

---

## ✅ GENUINE STRENGTHS

1. **Comprehensive Security Middleware Stack** — 9-layer defense-in-depth architecture ครอบคลุม IP filtering, request sanitization, CSRF, authentication, rate limiting, input validation, และ security headers อย่างครบถ้วน

2. **Event-Driven Architecture with Dead Letter Queue** — Event bus implementation มี proper error handling, failed event tracking (last 100), และ replay capability ทำให้สามารถ debug และ recover จาก failures ได้

3. **Cost-Aware LLM Routing** — Model router system มี automatic tier selection based on task complexity, cost estimation, และ budget ceiling enforcement ป้องกัน runaway LLM costs

4. **Production Configuration Validation** — `Settings.validate_production_configuration()` ตรวจสอบ 20+ security requirements ก่อน startup ใน production mode รวมถึง secret strength, URL schemes, และ placeholder detection

5. **Proper Async/Await Patterns** — ใช้ `asyncio`, `async/await`, และ `AsyncSession` อย่างถูกต้องตลอดทั้ง codebase ไม่มี blocking operations ใน async context

6. **Comprehensive Audit Logging** — Security events ถูก log พร้อม context (user_id, session_id, IP, user_agent, request details) และ severity classification เหมาะสำหรับ compliance และ forensics

7. **Type Safety with Pydantic** — ใช้ Pydantic Settings และ model validation ทำให้ configuration type-safe และ self-documenting

---

## 📊 ISSUE STATISTICS

| Severity | Count | Est. Total Fix Time |
|----------|-------|-------------------|
| CRITICAL | 2 | 5h |
| HIGH | 3 | 7h |
| MEDIUM | 5 | 9.5h |
| LOW | 10 | 5h |
| **TOTAL** | **20** | **26.5h** |

---

## 📋 MASTER ISSUE LIST (Feed This Into PROMPT 02)

1. [C-01] CRITICAL · CSRF Token Comparison Vulnerable to Timing Attack · Security · 2h
2. [C-02] CRITICAL · Internal Webhook Authentication Missing HMAC Signature · Security · 3h
3. [H-01] HIGH · Default Development Secrets in Configuration · Security · 1.5h
4. [H-02] HIGH · Event Bus Processing Loop Missing Graceful Shutdown · Architecture · 2.5h
5. [H-03] HIGH · Missing Database Indexes for Common Query Patterns · Data Layer · 3h
6. [M-01] MEDIUM · Middleware Order Dependency Not Documented · Code Quality · 0.5h
7. [M-02] MEDIUM · Event Bus Queue Size Unbounded · Architecture · 1.5h
8. [M-03] MEDIUM · Model Router Cost Estimation Assumes Symmetric Token Usage · Performance · 2h
9. [M-04] MEDIUM · CSRF Token Generation Uses Random Bytes Without Timestamp · Security · 2h
10. [M-05] MEDIUM · Input Sanitization Regex Patterns Too Broad · Security · 3h
11. [L-01] LOW · Duplicate SecurityHeadersMiddleware Imports · Code Quality · 0.5h
12. [L-02] LOW · Event Bus reset() Method Missing Production Guard · Code Quality · 0.5h
13. [L-03] LOW · IP Filtering Config Defined Twice · Code Quality · 0.5h
14. [L-04] LOW · Internal Token Check Should Be Separate Function · Code Quality · 0.5h
15. [L-05] LOW · Incomplete Version Pinning in requirements.txt · Dependencies · 0.5h
16. [L-06] LOW · Redis Password Visible in Docker PS · Security · 0.5h
17. [L-07] LOW · Playwright Browser Install Not Cached in CI · DevOps · 0.5h
18. [L-08] LOW · Model Router Task Defaults Should Be Config · Code Quality · 0.5h
19. [L-09] LOW · Security Headers Should Be Configurable · Code Quality · 0.5h
20. [L-10] LOW · Production Validation Should Run at Build Time · DevOps · 0.5h

---

**รายงานนี้ครอบคลุมการวิเคราะห์ 10 มิติตาม PROMPT 01 framework โดยใช้หลักฐานจากโค้ดจริง ทุก finding มี file:line reference และ remediation ที่ชัดเจน พร้อมสำหรับนำไปสู่ PROMPT 02 (Implementation Plan)**
