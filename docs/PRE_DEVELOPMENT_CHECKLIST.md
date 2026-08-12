# Pre-Development Checklist

Checklist นี้ใช้กับ codebase ปัจจุบันของ Personal OS ก่อนเริ่มงาน feature, stabilization, หรือ deployment รอบใหม่

## 1. Environment and Access

- [ ] copy `.env.example` ไปเป็น `.env`
- [ ] เติมค่าที่ต้องใช้จริงอย่างน้อย:
  - `DATABASE_URL`
  - `POSTGRES_DB`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`
  - `REDIS_URL`
  - `OPENCLAW_API_KEY` ถ้าจะใช้ primary LLM path
  - `GEMINI_API_KEY` ถ้าจะใช้ fallback LLM path
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REFRESH_TOKEN`
  - `GOOGLE_WORKSPACE_EMAIL`
- [ ] ทบทวน cost guardrails ใน `.env`
  - `MAX_DAILY_AI_COST_USD`
  - `MAX_MONTHLY_AI_COST_USD`
  - `MAX_SINGLE_LLM_CALL_COST_USD`

## 2. Local Toolchain

- [ ] Python `3.11+` พร้อมใช้งาน
- [ ] Docker และ Docker Compose plugin พร้อมใช้งาน
- [ ] Bun ติดตั้งแล้วสำหรับ frontend

ตรวจสอบเวอร์ชัน:

```bash
python --version
docker --version
docker compose version
bun --version
```

## 3. Backend Bootstrap

- [ ] สร้าง virtual environment

```bash
python -m venv .venv
```

- [ ] activate environment

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

- [ ] install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

- [ ] run migrations

```bash
cd backend
alembic upgrade head
```

## 4. Local Services

- [ ] start local services

```bash
docker compose up -d
```

- [ ] confirm compose renders correctly

```bash
docker compose -f docker-compose.yml config > /dev/null
```

- [ ] verify root health

```bash
curl http://localhost:8000/health
```

## 5. Backend Verification

- [ ] run backend tests

```bash
cd backend
python -m pytest tests -q
```

- [ ] export the OpenAPI spec from code

```bash
cd backend
python scripts/export_openapi.py --output openapi.json
```

- [ ] run smoke tests against the running stack

```bash
bash backend/scripts/smoke_tests.sh
```

- [ ] inspect interactive docs
  - `http://localhost:8000/docs`

## 6. Frontend Verification

- [ ] install frontend dependencies

```bash
cd frontend
bun install
```

- [ ] run lint

```bash
cd frontend
bun run lint
```

- [ ] run build

```bash
cd frontend
bun run build
```

## 7. Operational Scripts

- [ ] validate backup script syntax

```bash
bash -n backend/scripts/backup_database.sh
```

- [ ] validate restore script syntax

```bash
bash -n backend/scripts/restore_database.sh
```

- [ ] validate smoke test script syntax

```bash
bash -n backend/scripts/smoke_tests.sh
```

- [ ] know the backup flow

```bash
bash backend/scripts/backup_database.sh
```

- [ ] know the restore flow

```bash
bash backend/scripts/restore_database.sh backups/backup_YYYYMMDD_HHMMSS.sql.gz
```

## 8. CI/CD Baseline

- [ ] verify GitHub Actions workflow exists at `.github/workflows/ci.yml`
- [ ] confirm the workflow still reflects the local commands that pass:
  - backend: `python -m pytest tests -q`
  - backend: `python scripts/export_openapi.py --output openapi.json`
  - frontend: `bun run lint`
  - frontend: `bun run build`
  - ops: `bash -n backend/scripts/*.sh`

## 9. Optional Integrations

Telegram quick check:

```bash
cd backend
python -m app.telegram_bot.bot
```

Google Workspace quick checks:

```bash
curl http://localhost:8000/api/v1/integrations/google/health
curl http://localhost:8000/api/v1/integrations/google/gmail/inbox-summary
curl http://localhost:8000/api/v1/integrations/google/calendar/today
```

## 10. Ready-to-Start Gate

Do not start new feature work until all of these are true:

- [ ] backend tests are green
- [ ] OpenAPI export succeeds
- [ ] smoke tests pass against the target stack
- [ ] frontend lint and build are green
- [ ] `.env` no longer contains placeholder values for the integrations you need
