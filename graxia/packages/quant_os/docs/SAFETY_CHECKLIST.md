# Safety Checklist — ก่อนรัน MT5 Demo ครั้งแรก

## ✅ Phase 1: ยืนยัน Demo Account (ทำก่อนรัน.bot 1 วัน)

- [ ] เปิด MT5 แล้วเช็คชื่อ server ว่ามี "Demo" อยู่จริง
  - ตัวอย่างที่ถูก: `ICMarketsSC-Demo`, `Pepperstone-Demo02`
  - ตัวอย่างที่ผิด: `ICMarketsSC-Live`, `Pepperstone-Real01`
- [ ] เช็ค account number ตรงกับที่สมัคร demo
- [ ] เช็ค balance — demo ควรเริ่มที่ $10,000-$100,000 (ไม่ใช่ $0)
- [ ] ทดสอบ placing 1 order ด้วยมือก่อน ว่า order ได้จริง

## ✅ Phase 2: Config Safety (ทำก่อนรัน.bot)

- [ ] ตั้ง `max_risk_per_trade_pct = 0.5` (ไม่ใช่ 1.0 สำหรับวันแรก)
- [ ] ตั้ง `max_daily_loss_pct = 1.5` (conservative กว่า backtest)
- [ ] ตั้ง `max_positions = 1` (เริ่มที่ 1 position ก่อน)
- [ ] ตั้ง `min_score_to_trade = 300` (เข้มกว่า default)
- [ ] ปิด `ai_validation_enabled = False` ก่อน (ลด latency)

## ✅ Phase 3: เริ่มจาก 1 Strategy (วันที่ 1-7)

- [ ] รันแค่ `ema_cross` strategy เดียวก่อน
- [ ] ไม่เปิด league system (ให้ทุก strategy เท่ากัน)
- [ ] เช็ค log ทุก 1 ชั่วโมง
- [ ] บันทึก trade log แยกจาก backtest log

## ✅ Phase 4: เปรียบเทียบ Demo vs Backtest (สัปดาห์ที่ 1)

- [ ] Export trade log จาก MT5 (Account History → Export)
- [ ] เทียบกับ backtest results:
  - Win rate: demo ควรอยู่ใน 80% ของ backtest
  - Avg trade duration: ไม่ต่างกันมาก
  - Slippage: demo มักดีกว่าจริง → ต้อง expect performance gap
- [ ] ถ้า demo win rate < 40% → หยุด แล้วตรวจ backtest

## ✅ Phase 5: เปิดเพิ่ม Strategy (สัปดาห์ที่ 2-4)

- [ ] เพิ่ม策略ทีละ 1 ตัว ไม่ใช่เปิดทีเดียว 13 ตัว
- [ ] แต่ละ策略ต้องผ่าน 7 วัน demo ก่อนเพิ่มตัวถัดไป
- [ ] ถ้า strategy ไหนขาดทุน 3 วันติด → หยุด strategy นั้น

## ✅ Phase 6: Monitoring Alert (ตั้งก่อนรัน)

- [ ] Telegram alert สำหรับ:
  - Trade executed (ทุก order)
  - Daily P&L report (22:00 UTC)
  - Kill switch triggered
  - Connection lost (heartbeat miss > 5 min)
- [ ] ตั้ง hard stop: ถ้า drawdown > 5% → หยุดทั้งระบบ

## ✅ Phase 7: เกณฑ์ "หยุดและกลับไปทบทวน"

- [ ] ถ้า demo drawdown > 5% → หยุดทันที
- [ ] ถ้า demo win rate < 40% หลัง 50 trades → หยุด
- [ ] ถ้า demo P&L < -3% ของ balance → หยุด
- [ ] ถ้ามี order ที่ไม่ได้ตั้งใจ (phantom trade) → หยุด
- [ ] เกณฑ์นี้ต้องตั้งก่อนเริ่ม ไม่ใช่ตัดสินใจตอนกำลังขาดทุน

## ⛔ ห้ามทำเด็ดขาด

- [ ] ห้ามรันบน live account โดยไม่ได้ตั้งใจ
- [ ] ห้ามเพิ่ม position size ตอนกำลังชนะ (revenge trading)
- [ ] ห้ามปิด kill switch ตอนกำลังขาดทุน
- [ ] ห้ามเชื่อผล backtest โดยไม่ cross-validate กับ demo results
- [ ] ห้ามเพิ่ม策略ใหม่ระหว่างที่ระบบกำลังขาดทุน
