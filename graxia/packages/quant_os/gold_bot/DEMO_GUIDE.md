# Gold Bot — Demo Trading Guide

## 📋 ก่อนเริ่ม

### สิ่งที่ต้องมี
1. **MetaTrader 5** — ดาวน์โหลดจาก https://www.metatrader5.com
2. **Demo Account** — สมัครฟรีจาก broker (ICMarkets, Pepperstone, XM)
3. **Python 3.10+** — ติดตั้งจาก https://python.org
4. **Dependencies** — ติดตั้งด้วย: `pip install MetaTrader5 pandas pandas_ta`

### ขั้นตอนการตั้งค่า MT5

#### 1. สร้าง Demo Account
```
1. เปิด MT5
2. File → Open an Account
3. เลือก broker (เช่น ICMarketsSC-Demo)
4. สมัคร demo account
5. จด记住 login/password/server
```

#### 2. เปิด XAUUSD Chart
```
1. ใน MT5 Market Watch
2. คลิกขวาที่ XAUUSD
3. เลือก Chart Window
4. เปลี่ยน timeframe เป็น M15
```

#### 3. เปิด允许 Automated Trading
```
1. คลิกปุ่ม "AutoTrading" บน toolbar
2. หรือ press Ctrl+E
3. ต้องเห็นไอคอนสีเขียว
```

---

## 🚀 เริ่ม Demo Trading

### วิธีที่ 1: ใช้ Batch File (ง่ายที่สุด)
```batch
double-click start_demo.bat
```

### วิธีที่ 2: ใช้ Command Line
```bash
cd "graxia os"
python graxia/packages/quant_os/gold_bot/run_demo.py
```

### วิธีที่ 3: ใช้ Python IDE
```python
# สร้างไฟล์ my_demo.py
import asyncio
import sys
sys.path.insert(0, r"C:\Users\menum\graxia os")

from graxia.packages.quant_os.gold_bot.run_demo import DemoTrader

async def main():
    trader = DemoTrader()
    await trader.start()

asyncio.run(main())
```

---

## 📊 วิธีอ่านผลลัพธ์

### Terminal Output
```
  [Cycle 10] Price: 2350.25 | Score: 320 | Active: 10/13 | Spread: 0.30 | P&L: +$12.50
  
  🟢 TRADE #1
  BUY 0.05 lots @ 2350.25
  SL: 2345.00 | TP: 2360.00
  Score: 320
  Strategies: ema_cross(80), multi_tf_align(75), order_block(70)
```

### ความหมาย
- **Price**: ราคาปัจจุบันของ XAUUSD
- **Score**: คะแนนรวมจาก 13 strategies (ต้อง >= 250 ถึงเทรด)
- **Active**: จำนวน strategies ที่ active (10 จาก 13)
- **Spread**: ราคา bid-ask spread
- **P&L**: กำไร/ขาดทุนสะสม

### Strategy Scores
| Strategy | Score | ความหมาย |
|----------|-------|-----------|
| ema_cross(80) | 80% | EMA crossover สัญญาณแข็ง |
| multi_tf_align(75) | 75% | Multi-timeframe ตรงกัน |
| order_block(70) | 70% | ICT Order Block ทำงาน |

---

## ⚙️ ตั้งค่า

### แก้ไข Config ใน run_demo.py
```python
self.config = BotConfig(
    symbol="XAUUSD",           # คู่เงิน
    cycle_interval_seconds=30,  # ตรวจสอบทุก 30 วินาที
    min_score_to_trade=250,     # คะแนนขั้นต่ำ
    max_risk_per_trade_pct=0.5, # ความเสี่ยงต่อเทรด
    max_positions=2,            # สูงสุด 2 positions
)
```

### ตั้งค่า Environment Variables (ถ้าต้องการ AI)
```bash
set ANTHROPIC_API_KEY=your_key_here
set TELEGRAM_BOT_TOKEN=your_token_here
set TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## 🛡️ Risk Management

### ระบบป้องกันอัตโนมัติ
1. **Max Drawdown**: หยุดเทรดถ้าขาดทุนเกิน 8%
2. **Daily Loss Limit**: หยุดเทรดถ้าขาดทุนวันนี้เกิน 2%
3. **Max Positions**: ไม่เกิน 2 positions พร้อมกัน
4. **Kill Switch**: หยุดทั้งระบบถ้าเกิดปัญหา

### สิ่งที่ต้องทำก่อนเทรดจริง
1. ✅ Paper trading อย่างน้อย 60 วัน
2. ✅ มี trades อย่างน้อย 100 trades
3. ✅ Win rate > 50%
4. ✅ Profit Factor > 1.3
5. ✅ Max Drawdown < 15%
6. ✅ Walk-forward validation ผ่าน
7. ✅ Monte Carlo p-value > 0.95

---

## 🔧 Troubleshooting

### MT5 ไม่เชื่อมต่อ
```
- เปิด MT5 terminal แล้วหรือยัง?
- Login demo account แล้วหรือยัง?
- ติดตั้ง MetaTrader5 package แล้วหรือยัง? pip install MetaTrader5
```

### Order ไม่สำเร็จ
```
- AutoTrading เปิดอยู่หรือเปล่า? (Ctrl+E)
- XAUUSD chart เปิดอยู่หรือเปล่า?
- Demo account มี balance พอหรือเปล่า?
```

### Strategy ไม่สร้างสัญญาณ
```
- ลด min_score_to_trade ลง (เช่น 200)
- ตรวจสอบว่า data ถูกต้อง
- ดู log ว่ามี error ไหม
```

---

## 📈 ขั้นตอนถัดไป

เมื่อ demo trading ได้ผลดี:
1. วิเคราะห์ผลลัพธ์จาก demo
2. ปรับ parameters ตามผล backtest
3. ทดสอบ walk-forward validation
4. ทดสอบ Monte Carlo simulation
5. ค่อยๆ เพิ่ม position size
6. **อย่าข้ามขั้นตอนใดขั้นตอนหนึ่ง**
