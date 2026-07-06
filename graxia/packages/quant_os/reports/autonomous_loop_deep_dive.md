# Autonomous Trading Loop — Deep Dive Report
## Status: Paper Mode Ready | Live Mode: NOT READY

---

## ✅ สิ่งที่ทำเสร็จแล้ว (8 ไฟล์, ~1,700 LOC)

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Config | `autonomous/config.py` | 55 | ✅ |
| Chart Monitor | `autonomous/chart_monitor.py` | 268 | ✅ |
| Decision Engine | `autonomous/decision_engine.py` | 339 | ✅ |
| Order Executor | `autonomous/order_executor.py` | 424 | ✅ |
| Orchestrator | `autonomous/orchestrator.py` | 325 | ✅ |
| Live Approval | `autonomous/live_approval.py` | 205 | ✅ |
| Launch Script | `scripts/launch_autonomous_paper.py` | 136 | ✅ |
| TV CDP Launcher | `scripts/launch_tv_cdp.ps1` | ~50 | ✅ |
| Tests | `tests/test_autonomous_loop.py` | 232 | ✅ 19 tests pass |

---

## ❌ ช่องโหว่ที่ต้องแก้ก่อน Paper Mode จริง

### 1. 🟡 Position Sizing ไม่เชื่อม Account Equity
**ปัญหา:** `_calculate_position_size()` ใช้ confidence * 0.5 โดยไม่ดู account equity, margin, หรือ risk per trade
**ความเสี่ยง:** ขนาด position อาจใหญ่เกินไปสำหรับ account เล็ก หรือเล็กเกินไปสำหรับ account ใหญ่
**แก้ไข:** ต้องเชื่อม `AccountState` จาก MT5 (balance, equity, margin) เข้า sizing logic
**ไฟล์ที่เกี่ยวข้อง:** `order_executor.py:235-243`, `risk/position_sizer.py`

### 2. 🟡 Asset Class Hardcoded เป็น "metals"
**ปัญหา:** `_check_risk()` hardcode `asset_class="metals"` สำหรับทุก symbol
**ความเสี่ยง:** BTC/ETH ควรใช้ `asset_class="crypto"`, ซึ่งมี session guard ต่างกัน (crypto = 24/7)
**แก้ไข:** สร้าง symbol registry ที่ map symbol → asset class
**ไฟล์ที่เกี่ยวข้อง:** `order_executor.py:213`, `risk/market_session_guard.py`

### 3. 🟡 AccountState/PortfolioState เป็น Default Values เสมอ
**ปัญหา:** `_check_risk()` สร้าง `AccountState()` และ `PortfolioState()` ด้วย default values ($100k equity) ทุกครั้ง
**ความเสี่ยง:** Risk engine ไม่ได้เห็นสถานะจริง → อนุญาต trades ที่ควร reject
**แก้ไข:** ต้องดึง account state จาก MT5 จริงก่อน risk check
**ไฟล์ที่เกี่ยวข้อง:** `order_executor.py:218-219`, `risk/engine.py:118-141`

### 4. 🟡 No Persistence — Restart = lose everything
**ปัญหา:** ไม่มีการ persist decisions, execution log, daily stats, หรือ health state
**ความเสี่ยง:** Crash → restart → จำไม่ได้ว่าเทรดอะไรไปแล้ว → duplicate trades
**แก้ไข:** เพิ่ม SQLite/DuckDB persistence layer สำหรับ:
  - Trade decisions (audit trail)
  - Execution log (what was submitted)
  - Daily stats (trades today, P&L)
  - System health (uptime, errors)
**ไฟล์ที่เกี่ยวข้อง:** `orchestrator.py:301-307` (`_save_state` ว่างเปล่า)

### 5. 🟡 Live Approval — Telegram Callback ไม่เชื่อม
**ปัญหา:** `LiveApprovalGate` ส่ง inline keyboard ไป Telegram แต่ไม่มี callback handler ที่รับ response
**ความเสี่ยง:** Live mode จะไม่ทำงาน — ไม่มีใครกด approve ได้
**แก้ไข:** เชื่อม `LiveApprovalGate.handle_callback()` เข้ากับ `TelegramCallbackHandler` หรือ Telegram polling loop
**ไฟล์ที่เกี่ยวข้อง:** `live_approval.py:125-129`, `core/telegram_callback.py`, `api/telegram_server.py`

### 6. 🟡 No Real Broker Integration
**ปัญหา:** `_submit_order()` เรียก `broker.submit_order(order)` แต่ไม่มีการ init BrokerManager จริง
**ความเสี่ยง:** Paper mode จะ fail ทันทีเพราะไม่มี broker adapter
**แก้ไข:** ต้อง init BrokerManager ด้วย PaperAdapter (paper mode) หรือ MT5Adapter (live mode)
**ไฟล์ที่เกี่ยวข้อง:** `execution/adapters/manager.py`, `execution/adapters/paper.py`

### 7. 🟡 No CDP Reconnection Logic
**ปัญหา:** ถ้า TV CDP connection หลุดระหว่าง loop → `_cdp_available = False` ตลอดกาล
**ความเสี่ยง:** สูญเสีย screenshot capability ถาวร จนกว่าจะ restart
**แก้ไข:** เพิ่ม periodic CDP reconnection attempt (ทุก 5-10 นาที)
**ไฟล์ที่เกี่ยวข้อง:** `chart_monitor.py:229-237`

### 8. 🟡 No Rate Limiting on LLM Calls
**ปัญหา:** ไม่มี rate limit สำหรับ LLM API calls — ถ้า symbols/timeframes มาก จะโดน rate limit ทันที
**ความเสี่ยง:** Groq: 1000 req/day, Cerebras: 14400 req/day — ถ้า poll ทุก 60s × 3 symbols × 3 timeframes = 432 calls/day
**แก้ไข:** เพิ่ม rate limiter สำหรับแต่ละ provider
**ไฟล์ที่เกี่ยวข้อง:** `decision_engine.py:183-184`, `core/agents/llm_router.py`

---

## ❌ ช่องโหว่ที่ต้องแก้ก่อน Live Mode

### 9. 🔴 No Circuit Breaker
**ปัญหา:** ไม่มี circuit breaker ที่หยุด trading เมื่อ market volatile หรือ system error rate สูง
**ความเสี่ยง:** System อาจเทรดในช่วง flash crash หรือข่าวสำคัญ
**แก้ไข:** เชื่อม CircuitBreaker เข้ากับ RiskEngine pre-checks
**ไฟล์ที่เกี่ยวข้อง:** `risk/circuit_breaker.py`

### 10. 🔴 No News Blackout
**ปัญหา:** ไม่มี news blackout gate ที่หยุด trading ก่อน/หลังข่าวสำคัญ
**ความเสี่ยง:** เทรดระหว่าง NFP, FOMC, CPI → slippage สูง
**แก้ไข:** เชื่อม news pipeline เข้ากับ autonomous loop
**ไฟล์ที่เกี่ยวข้อง:** `news_events/integration.py`, `scripts/news_pipeline.py`

### 11. 🔴 No Multi-Symbol Correlation Check
**ปัญหา:** ไม่มี correlation check ระหว่าง symbols (เช่น XAUUSD + BTCUSD อาจ correlated)
**ความเสี่ยง:** เปิด position หลายตัวที่ correlated → portfolio risk สูงเกินไป
**แก้ไข:** เชื่อม CorrelationProvider เข้ากับ risk check
**ไฟล์ที่เกี่ยวข้อง:** `risk/correlation_provider.py`, `risk/ewma_correlation.py`

### 12. 🔴 No Trade Reconciliation
**ปัญหา:** ไม่มี reconciliation ระหว่าง execution log และ broker state
**ความเสี่ยง:** Order อาจไม่ได้ fill จริง แต่ system คิดว่าเทรดแล้ว
**แก้ไข:** เพิ่ม periodic reconciliation loop (ทุก 5 นาที)
**ไฟล์ที่เกี่ยวข้อง:** `execution/reconcile.py`, `execution/position_reconciler.py`

### 13. 🔴 No Telegram Alerting for Trades
**ปัญหา:** ไม่มี Telegram notification เมื่อเทรด (ทั้ง paper และ live)
**ความเสี่ยง:** ไม่รู้ว่า system เทรดอะไร — ต้องนั่งดู logs
**แก้ไข:** เพิ่ม Telegram notification สำหรับ: trade executed, kill switch, daily summary
**ไฟล์ที่เกี่ยวข้อง:** `core/telegram_notify.py`, `monitoring/telegram.py`

### 14. 🔴 No Health Dashboard
**ปัญหา:** ไม่มี way ที่จะดู system health แบบ real-time (นอกจาก logs)
**ความเสี่ยง:** ไม่รู้ว่า system กำลังทำงานปกติหรือไม่
**แก้ไข:** เพิ่ม /autonomous/status endpoint ใน FastAPI
**ไฟล์ที่เกี่ยวข้อง:** `api/main.py`, `autonomous/orchestrator.py:156-163`

---

## 🔒 Security Issues

### 15. 🟡 Live Approval — No User Validation
**ปัญหา:** `LiveApprovalGate` ไม่ validate ว่า callback มาจาก authorized user
**ความเสี่ยง:** ใครก็ได้ที่รู้ request_id สามารถ approve trade ได้
**แก้ไข:** Validate callback data กับ `TELEGRAM_ALLOWED_USERS`
**ไฟล์ที่เกี่ยวข้อง:** `live_approval.py:125-129`

### 16. 🟡 No Input Sanitization on LLM Response
**ปัญหา:** LLM response ถูก parse เป็น JSON แต่ไม่มี validation ของ numeric values
**ความเสี่ยง:** LLM อาจ return entry=999999 หรือ sl=0 ทำให้ order ผิดปกติ
**แก้ไข:** เพิ่ม sanity check สำหรับ entry, sl, tp (ต้องอยู่ใน price range ที่สมเหตุสมผล)
**ไฟล์ที่เกี่ยวข้อง:** `decision_engine.py:234-268`

### 17. 🟡 No Rate Limiting on Telegram API
**ปัญหา:** ไม่มี rate limit สำหรับ Telegram API calls
**ความเสี่ยง:** ถ้า system ส่ง message เร็วเกินไป จะโดน Telegram block
**แก้ไข:** เพิ่ม rate limiter สำหรับ Telegram API
**ไฟล์ที่เกี่ยวข้อง:** `live_approval.py:167-182`

---

## 🧪 Test Coverage Gaps

### 18. 🟡 No Integration Test with Real MT5
**ปัญหา:** ไม่มี integration test ที่เชื่อม MT5 จริง
**แก้ไข:** เพิ่ม integration test ด้วย MT5 demo account

### 19. 🟡 No Integration Test with Real LLM
**ปัญหา:** ไม่มี integration test ที่เรียก LLM จริง (mock ทั้งหมด)
**แก้ไข:** เพิ่ม integration test ด้วย Groq/Cerebras จริง

### 20. 🟡 No Chaos Test
**ปัญหา:** ไม่มี chaos test สำหรับ autonomous loop (CDP disconnect, LLM timeout, broker error)
**แก้ไข:** เพิ่ม chaos test ตาม pattern ของ `tests/chaos/`

### 21. 🟡 No Load Test
**ปัญหา:** ไม่มี load test ที่ทดสอบ 3 symbols × 3 timeframes พร้อมกัน
**แก้ไข:** เพิ่ม load test ที่จำลอง 100+ snapshots

---

## 📋 แผนการแก้ไข (เรียงตามriority)

### Phase A: Paper Mode จริง (ต้องทำก่อนเริ่ม paper trade)
| # | Task | Est. | Files |
|---|------|------|-------|
| A1 | เชื่อม MT5 AccountState เข้า RiskEngine | 2h | order_executor.py, mt5.py |
| A2 | สร้าง Symbol Registry (symbol → asset class) | 1h | autonomous/symbol_registry.py |
| A3 | Init BrokerManager จริง (PaperAdapter) | 1h | orchestrator.py |
| A4 | เพิ่ม Persistence Layer (SQLite) | 3h | autonomous/persistence.py |
| A5 | เพิ่ม CDP Reconnection Logic | 1h | chart_monitor.py |
| A6 | เพิ่ม Rate Limiter สำหรับ LLM | 1h | decision_engine.py |
| A7 | เพิ่ม Sanity Check สำหรับ LLM numeric output | 1h | decision_engine.py |
| A8 | เพิ่ม Telegram Trade Notifications | 2h | autonomous/notifications.py |
| **Total** | | **12h** | |

### Phase B: Live Mode (ต้องทำก่อนสลับเป็น live)
| # | Task | Est. | Files |
|---|------|------|-------|
| B1 | เชื่อม LiveApprovalGate เข้า Telegram Callback | 3h | live_approval.py, telegram_server.py |
| B2 | เพิ่ม Circuit Breaker Integration | 2h | orchestrator.py, circuit_breaker.py |
| B3 | เพิ่ม News Blackout Gate | 2h | orchestrator.py, news_events/ |
| B4 | เพิ่ม Multi-Symbol Correlation Check | 2h | order_executor.py, correlation_provider.py |
| B5 | เพิ่ม Trade Reconciliation Loop | 3h | autonomous/reconciler.py |
| B6 | เพิ่ม Health Dashboard Endpoint | 2h | api/autonomous_routes.py |
| B7 | Validate Telegram Callback User | 1h | live_approval.py |
| B8 | เพิ่ม Rate Limiter สำหรับ Telegram | 1h | live_approval.py |
| **Total** | | **16h** | |

### Phase C: Production Hardening
| # | Task | Est. | Files |
|---|------|------|-------|
| C1 | Integration Test with Real MT5 + LLM | 4h | tests/ |
| C2 | Chaos Test (disconnect, timeout, error) | 4h | tests/chaos/ |
| C3 | Load Test (100+ concurrent snapshots) | 2h | tests/ |
| C4 | Security Audit (secrets, input validation) | 4h | security/ |
| C5 | Docker/systemd service config | 2h | docker/, scripts/ |
| C6 | 60-day paper trade validation checklist | 2h | docs/ |
| **Total** | | **18h** | |

---

## 🎯 สรุป

| Phase | Status | Hours |
|-------|--------|-------|
| Infrastructure (what we built) | ✅ Done | ~12h |
| Phase A: Paper Mode จริง | ❌ 8 tasks | 12h |
| Phase B: Live Mode | ❌ 8 tasks | 16h |
| Phase C: Production Hardening | ❌ 6 tasks | 18h |
| **Total remaining** | | **46h** |

### สิ่งที่ทำได้ทันที (ไม่ต้องแก้ code)
1. เปิด TV Desktop พร้อม CDP port 9222
2. รัน `python scripts/launch_autonomous_paper.py --dry-run` เพื่อทดสอบ 1 cycle
3. ถ้า dry-run ผ่าน → เริ่ม paper trade จริง

### สิ่งที่ต้องแก้ก่อน paper trade จริง
1. **A1**: เชื่อม MT5 AccountState (สำคัญที่สุด — risk engine ไม่เห็น account จริง)
2. **A3**: Init BrokerManager จริง (ไม่งั้น order ไม่ถูกส่ง)
3. **A4**: Persistence Layer ( crash → restart → duplicate trades)

### สิ่งที่ต้องแก้ก่อน live mode
1. **B1**: Telegram Callback (ไม่งั้นไม่มีใคร approve ได้)
2. **B2**: Circuit Breaker (ป้องกัน flash crash)
3. **B3**: News Blackout (ป้องกันเทรดระหว่างข่าว)
