# Quant OS — Quick Start Guide

🚀 **ระบบเทรด Forex อัตโนมัติพร้อมใช้งาน**

---

## 📋 สิ่งที่มีในระบบ

✅ **3 กลยุทธ์เทรด**: MTM, MRB, MLB + Ensemble Voting  
✅ **Risk Engine**: Kill Switch, Circuit Breaker, Position Sizing  
✅ **OMS**: Order Management พร้อม State Machine  
✅ **MT5 Integration**: Paper + Live trading  
✅ **TradingView Webhook**: HMAC authentication  
✅ **Telegram Alerts**: แจ้งเตือนแบบ real-time  
✅ **Monitoring**: Grafana + Prometheus + Loki  
✅ **Docker**: Production-ready deployment  
✅ **CI/CD**: GitHub Actions pipeline  

---

## 🚀 เริ่มต้นใช้งาน (5 นาที)

### 1. สร้างไฟล์ .env

```bash
# Windows
copy .env.quant_os .env

# Linux/Mac
cp .env.quant_os .env
```

### 2. แก้ไขไฟล์ .env

```bash
# เปิดไฟล์ .env และแก้ไขค่าต่อไปนี้:

# Trading Mode (เริ่มต้นด้วย PAPER)
TRADING_MODE=PAPER
LIVE_TRADING_ENABLED=false

# Security Keys (สร้างใหม่)
# วิธีสร้างบน Windows:
python scripts/generate_keys.py

# หรือรันคำสั่งนี้:
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. เริ่มระบบด้วย Docker

**Windows:**
```cmd
scripts\start_quant_os.bat
```

**Linux/Mac:**
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

**หรือใช้ Docker Compose โดยตรง:**
```bash
docker compose -f docker-compose.quant.yml up -d
```

### 4. ตรวจสอบสถานะ

```bash
# Health check
curl http://localhost:8000/health

# ดู logs
docker compose -f docker-compose.quant.yml logs -f

# ดูสถานะ services
docker compose -f docker-compose.quant.yml ps
```

---

## 📱 Telegram Bot Setup

### 1. สร้าง Bot

1. ไปที่ Telegram ค้นหา `@BotFather`
2. พิมพ์ `/newbot`
3. ตั้งชื่อ bot (เช่น `MyQuantBot`)
4. ตั้ง username (ต้องลงท้ายด้วย `bot` เช่น `myquant_bot`)
5. คัดลอก **Token** ที่ได้

### 2. หา Chat ID

1. ค้นหา `@userinfobot`
2. กด Start จะได้ Chat ID (เช่น `123456789`)

### 3. อัปเดต .env

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 4. รัน Bot

```bash
python scripts/setup_telegram_bot.py
```

หรือส่งข้อความ test:
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/sendMessage" \
  -d "chat_id=<YOUR_CHAT_ID>" \
  -d "text=Quant OS is ready!"
```

---

## 📊 TradingView Setup

### 1. เปิด Pine Script

1. ไปที่ [TradingView](https://www.tradingview.com)
2. เปิดกราฟ Forex (เช่น EURUSD)
3. กด **Pine Editor** ที่ด้านล่าง

### 2. ใส่ Pine Script

เปิดไฟล์ `graxia/packages/quant_os/pine_script/QuantBot_Ensemble.pine`

Copy ทั้งหมดแล้ว Paste ลงใน Pine Editor

### 3. ตั้งค่า Webhook Alert

1. กด **Add Alert** (นาฬิกาบน toolbar)
2. Condition: เลือก `QuantBot v3.0`
3. Webhook URL:
   ```
   http://YOUR_SERVER_IP:8000/api/v1/webhook/tradingview
   ```
   - Local: `http://localhost:8000/api/v1/webhook/tradingview`
   - VPS: `http://your-vps-ip:8000/api/v1/webhook/tradingview`
4. Message:
   ```json
   {
     "action": "buy",
     "symbol": "{{ticker}}",
     "price": {{close}},
     "sl": {{plot_0}},
     "tp": {{plot_1}},
     "strategy": "ensemble",
     "timestamp": {{time}}
   }
   ```

---

## 🔒 Safety Checklist

ก่อนใช้งานจริง ตรวจสอบ:

- [ ] **TRADING_MODE=PAPER** (เริ่มต้นด้วย Paper)
- [ ] **LIVE_TRADING_ENABLED=false**
- [ ] Kill Switch ทำงาน (ทดสอบ trigger/reset)
- [ ] Telegram แจ้งเตือนได้
- [ ] Paper trading 60 วัน+ มีผลดี
- [ ] Backtest ผ่าน (CAGR 10%+, Drawdown < 15%)

---

## 📈 Monitoring

### Grafana Dashboard
- URL: http://localhost:3001
- Username: `admin`
- Password: `admin` (หรือตามที่ตั้งใน .env)

### Prometheus Metrics
- URL: http://localhost:9091

### API Documentation
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🛠️ Commands Cheat Sheet

```bash
# Start
./scripts/deploy.sh

# Stop
docker compose -f docker-compose.quant.yml down

# View logs
docker compose -f docker-compose.quant.yml logs -f quant-api

# Restart service
docker compose -f docker-compose.quant.yml restart quant-api

# Update
docker compose -f docker-compose.quant.yml pull
docker compose -f docker-compose.quant.yml up -d

# Run tests
python -m pytest graxia/packages/quant_os/tests/ -v

# Database migration
docker compose -f docker-compose.quant.yml exec quant-api alembic upgrade head

# Backup
docker compose -f docker-compose.quant.yml exec quant-db pg_dump -U postgres quant_os > backup.sql
```

---

## 🚨 Kill Switch

หากต้องการหยุดการเทรดฉุกเฉิน:

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/risk/killswitch/trigger \
  -H "X-Admin-Api-Key: YOUR_ADMIN_KEY" \
  -d '{"reason": "Manual emergency stop"}'

# Via Telegram
ส่งข้อความ: /killswitch trigger
```

---

## 📞 Support

หากมีปัญหา:

1. ตรวจสอบ logs: `docker compose logs -f`
2. ตรวจสอบ health: `curl http://localhost:8000/health`
3. รัน tests: `python -m pytest graxia/packages/quant_os/tests/`

---

**⚠️ คำเตือน**: ระบบนี้เริ่มต้นใน **PAPER MODE** เท่านั้น อย่าเปิด LIVE จนกว่าจะทดสอบอย่างละเอียดแล้ว

**🎯 เป้าหมาย**: ทดสอบ 60 วัน+ ใน Paper ก่อนขึ้น Live Micro

---

*Quant OS v1.0 — Trade Smart, Stay Safe*
