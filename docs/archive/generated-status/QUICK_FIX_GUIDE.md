# 🚀 Quick Fix Guide - Getting Started

## Problem 1: Docker Desktop Not Running

**Error:** `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`

**Solution:**
1. Open Docker Desktop application
2. Wait for it to fully start (whale icon in system tray should be steady)
3. Then run: `docker-compose up -d`

**Alternative (Run without Docker):**
```bash
# Start services manually instead
# See "Manual Setup" section below
```

---

## Problem 2: Database Connection Failed

**Error:** `asyncpg.exceptions.InternalServerError: Tenant or user not found`

**This means:** Your `.env` file has invalid Supabase credentials

**Solution:**

### Option A: Use Local PostgreSQL (Recommended for Development)

1. **Start Docker Desktop first**
2. **Update `.env` file:**
```bash
# Use local PostgreSQL from docker-compose
DATABASE_URL=postgresql+asyncpg://personal_os:changeme@localhost:5432/personal_os
```

3. **Start PostgreSQL:**
```bash
docker-compose up -d postgres redis
```

4. **Run migrations:**
```bash
cd backend
alembic upgrade head
```

### Option B: Fix Supabase Connection

1. **Go to Supabase Dashboard:** https://supabase.com/dashboard
2. **Get correct connection string:**
   - Project Settings → Database → Connection string
   - Choose "Session mode" (port 5432)
   - Copy the connection string

3. **Update `.env`:**
```bash
# Replace with YOUR actual Supabase credentials
DATABASE_URL=postgresql+asyncpg://postgres.[YOUR-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
```

4. **Test connection:**
```bash
cd backend
python -c "from app.database import engine; import asyncio; asyncio.run(engine.connect())"
```

---

## ✅ Complete Setup Steps

### Step 1: Check Prerequisites

```bash
# Check Docker is running
docker ps

# Check Python version (need 3.11+)
python --version

# Check if in correct directory
pwd  # Should show: C:\brav os
```

### Step 2: Setup Environment

```bash
# Copy example env if not exists
cp .env.example .env

# Edit .env with your actual credentials
# Use notepad or any text editor
notepad .env
```

**Required variables:**
```bash
# For local development (easiest)
DATABASE_URL=postgresql+asyncpg://personal_os:changeme@localhost:5432/personal_os
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# AI (get from https://openclaw.ai or use Gemini)
OPENCLAW_API_KEY=your_key_here
GEMINI_API_KEY=your_gemini_key_here

# Telegram (get from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_POLLING_ENABLED=false

# Auth (generate with: openssl rand -hex 32)
SECRET_KEY=your_secret_key_here
```

### Step 3: Start Infrastructure

```bash
# Start Docker Desktop first!
# Then start database and redis
docker-compose up -d postgres redis

# Wait 10 seconds for PostgreSQL to initialize
timeout /t 10

# Verify services are running
docker ps
```

### Step 4: Setup Database

```bash
cd backend

# Install dependencies (if not done)
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Should see:
# INFO  [alembic.runtime.migration] Running upgrade 006 -> 007, add_missing_tables
```

### Step 5: Start Backend

```bash
# Still in backend directory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Should see:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
```

### Step 6: Start Frontend (New Terminal)

```bash
cd frontend

# Install dependencies (if not done)
bun install

# Start dev server
bun run dev

# Should see:
# VITE ready in XXX ms
# Local: http://localhost:3000
```

### Step 7: Test Everything

1. **Backend Health:**
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok",...}
```

2. **Frontend:**
- Open: http://localhost:3000
- Should redirect to: http://localhost:3000/login

3. **Register First User:**
- Click "Register"
- Email: admin@example.com
- Password: changeme123
- Click "Create account"

4. **Test Dashboard:**
- Should redirect to dashboard
- Should see "Personal OS" header
- Should see navigation menu

---

## 🐛 Common Issues

### Issue: "Docker daemon not running"
**Fix:** Start Docker Desktop application

### Issue: "Port 5432 already in use"
**Fix:** 
```bash
# Stop existing PostgreSQL
docker-compose down
# Or kill process using port
netstat -ano | findstr :5432
taskkill /PID <PID> /F
```

### Issue: "Module not found"
**Fix:**
```bash
cd backend
pip install -r requirements.txt
```

### Issue: "Alembic can't connect"
**Fix:** Check DATABASE_URL in .env is correct

### Issue: "Frontend won't start"
**Fix:**
```bash
cd frontend
rm -rf node_modules
bun install
```

### Issue: "API calls return 401"
**Fix:** 
- Clear browser localStorage
- Register/Login again
- Check SECRET_KEY is set in .env

---

## 📋 Verification Checklist

After setup, verify:

- [ ] Docker Desktop is running
- [ ] PostgreSQL container is running: `docker ps | grep postgres`
- [ ] Redis container is running: `docker ps | grep redis`
- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] Can access http://localhost:8000/docs
- [ ] Can access http://localhost:3000
- [ ] Can register new user
- [ ] Can login
- [ ] Can see dashboard
- [ ] API calls work (check browser console)

---

## 🚀 Quick Start (TL;DR)

```bash
# 1. Start Docker Desktop (GUI)

# 2. Start services
docker-compose up -d postgres redis

# 3. Setup database
cd backend
alembic upgrade head

# 4. Start backend (Terminal 1)
uvicorn app.main:app --reload

# 5. Start frontend (Terminal 2)
cd frontend
bun run dev

# 6. Open browser
# http://localhost:3000
```

---

## 💡 Pro Tips

1. **Use local PostgreSQL for development** - Easier than Supabase
2. **Keep Docker Desktop running** - Required for containers
3. **Use separate terminals** - One for backend, one for frontend
4. **Check logs** - If something fails, read the error messages
5. **Clear browser cache** - If frontend acts weird
6. **Restart services** - When in doubt, restart everything

---

## 📞 Still Having Issues?

1. **Check logs:**
```bash
# Backend logs
tail -f backend/uvicorn-local.log

# Docker logs
docker-compose logs -f postgres
docker-compose logs -f redis
```

2. **Verify environment:**
```bash
# Check .env file
cat .env | grep DATABASE_URL
cat .env | grep REDIS_URL
```

3. **Test connections:**
```bash
# Test PostgreSQL
docker exec -it personal_os_postgres psql -U personal_os -d personal_os -c "SELECT 1;"

# Test Redis
docker exec -it personal_os_redis redis-cli ping
```

4. **Reset everything:**
```bash
# Nuclear option - start fresh
docker-compose down -v
docker-compose up -d postgres redis
cd backend
alembic upgrade head
```

---

**Last Updated:** 2026-04-07  
**Status:** Ready to use!

Good luck! 🚀
