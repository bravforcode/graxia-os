# 🚀 START HERE - Complete Setup Guide

**Last Updated:** 2026-04-07  
**Estimated Time:** 15 minutes  
**Difficulty:** Easy

---

## ✅ Prerequisites Check

Before starting, make sure you have:

- [ ] **Docker Desktop** installed and running
- [ ] **Python 3.11+** installed
- [ ] **Bun** or **Node.js 18+** installed
- [ ] **Git** installed
- [ ] **Windows Terminal** or **PowerShell**

---

## 📋 Step-by-Step Setup

### Step 1: Start Docker Desktop

1. Open **Docker Desktop** application
2. Wait until the whale icon in system tray is **steady** (not animated)
3. Verify it's running:

```powershell
docker ps
# Should show: CONTAINER ID   IMAGE   ...
# (May be empty, that's OK)
```

**If Docker fails to start:**
- Restart Docker Desktop
- Check Windows WSL2 is enabled
- See: https://docs.docker.com/desktop/troubleshoot/overview/

---

### Step 2: Start Database & Redis

```powershell
# Make sure you're in the project root
cd "C:\brav os"

# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Wait 10 seconds for PostgreSQL to initialize
timeout /t 10

# Verify containers are running
docker ps
# Should show: personal_os_postgres and personal_os_redis
```

**Expected output:**
```
Creating network "brav-os_default" with the default driver
Creating personal_os_postgres ... done
Creating personal_os_redis    ... done
```

---

### Step 3: Setup Python Environment

```powershell
# Navigate to backend
cd backend

# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# This will take 2-3 minutes
```

**Expected output:**
```
Successfully installed fastapi-0.115.0 uvicorn-0.30.0 ...
```

---

### Step 4: Run Database Migrations

```powershell
# Still in backend directory with venv activated
alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial_schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002_control_plane_foundation
INFO  [alembic.runtime.migration] Running upgrade 002 -> 003_skills_jobs_foundation
INFO  [alembic.runtime.migration] Running upgrade 003 -> 004_personal_assistant_tables
INFO  [alembic.runtime.migration] Running upgrade 004 -> 005_personal_assistant_tables
INFO  [alembic.runtime.migration] Running upgrade 005 -> 006_add_users_table
INFO  [alembic.runtime.migration] Running upgrade 006 -> 007, add_missing_tables
```

**If you see errors:**
- Check Docker containers are running: `docker ps`
- Check DATABASE_URL in `.env` file
- Restart PostgreSQL: `docker-compose restart postgres`

---

### Step 5: Start Backend Server

```powershell
# Still in backend directory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Will watch for changes in these directories: ['C:\\brav os\\backend']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Personal OS starting up...
INFO:     Scheduler: 9 jobs registered
INFO:     Scheduler: started
INFO:     Application startup complete.
```

**Test backend:**
Open new terminal and run:
```powershell
curl http://localhost:8000/health
```

Should return:
```json
{"status":"ok","service":"Personal OS v3","readiness":{"ready":true,"mode":"full","issues":[]}}
```

**Keep this terminal running!**

---

### Step 6: Start Frontend (New Terminal)

Open a **NEW terminal window** (keep backend running):

```powershell
# Navigate to frontend
cd "C:\brav os\frontend"

# Install dependencies (first time only)
bun install
# Or if using npm: npm install

# Start development server
bun run dev
# Or if using npm: npm run dev
```

**Expected output:**
```
VITE v5.x.x  ready in 1234 ms

➜  Local:   http://localhost:3000/
➜  Network: use --host to expose
➜  press h + enter to show help
```

**Keep this terminal running too!**

---

### Step 7: Open Browser & Register

1. **Open browser:** http://localhost:3000

2. **You should see:** Login page

3. **Click "Register"**

4. **Fill in:**
   - Email: `admin@example.com`
   - Password: `changeme123`
   - Full Name: `Admin User` (optional)

5. **Click "Create account"**

6. **You should be redirected to:** Dashboard

---

## ✅ Verification

After setup, you should see:

### Backend (Terminal 1):
```
INFO:     Application startup complete.
INFO:     127.0.0.1:xxxxx - "GET /health HTTP/1.1" 200 OK
```

### Frontend (Terminal 2):
```
VITE v5.x.x  ready in 1234 ms
➜  Local:   http://localhost:3000/
```

### Browser:
- ✅ Can access http://localhost:3000
- ✅ Can register new user
- ✅ Can login
- ✅ Can see dashboard with navigation
- ✅ Can click through different pages (Jobs, Tasks, etc.)

### API:
```powershell
# Test health endpoint
curl http://localhost:8000/health

# Test API docs
# Open: http://localhost:8000/docs
```

---

## 🎉 Success!

If all steps completed successfully, you now have:

- ✅ PostgreSQL database running
- ✅ Redis cache running
- ✅ Backend API running on port 8000
- ✅ Frontend app running on port 3000
- ✅ User authentication working
- ✅ Database migrations applied

**You're ready to use Personal OS!**

---

## 🔧 Common Issues & Solutions

### Issue 1: "Docker daemon not running"

**Solution:**
1. Open Docker Desktop
2. Wait for it to fully start
3. Try again

### Issue 2: "Port 5432 already in use"

**Solution:**
```powershell
# Stop all containers
docker-compose down

# Kill process using port (if needed)
netstat -ano | findstr :5432
# Note the PID, then:
taskkill /PID <PID> /F

# Start again
docker-compose up -d postgres redis
```

### Issue 3: "Module not found" (Python)

**Solution:**
```powershell
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Issue 4: "Cannot find module" (Frontend)

**Solution:**
```powershell
cd frontend
rm -rf node_modules
bun install
```

### Issue 5: "Alembic can't connect to database"

**Solution:**
```powershell
# Check containers are running
docker ps

# Check .env file
cat .env | Select-String DATABASE_URL

# Should show:
# DATABASE_URL=postgresql+asyncpg://personal_os:changeme@localhost:5432/personal_os

# Restart PostgreSQL
docker-compose restart postgres

# Wait 10 seconds
timeout /t 10

# Try migration again
cd backend
alembic upgrade head
```

### Issue 6: "API returns 401 Unauthorized"

**Solution:**
1. Clear browser localStorage (F12 → Application → Local Storage → Clear)
2. Logout and login again
3. Check SECRET_KEY is set in `.env`

### Issue 7: "Frontend shows blank page"

**Solution:**
1. Check browser console (F12) for errors
2. Check backend is running
3. Check CORS settings
4. Try hard refresh (Ctrl+Shift+R)

---

## 🛑 How to Stop Everything

```powershell
# Stop backend (in backend terminal)
# Press: Ctrl+C

# Stop frontend (in frontend terminal)
# Press: Ctrl+C

# Stop Docker containers
docker-compose down

# Or stop specific services
docker-compose stop postgres redis
```

---

## 🔄 How to Restart

```powershell
# Start Docker containers
docker-compose up -d postgres redis

# Start backend (Terminal 1)
cd backend
.\venv\Scripts\activate
uvicorn app.main:app --reload

# Start frontend (Terminal 2)
cd frontend
bun run dev
```

---

## 📚 Next Steps

Now that your system is running:

1. **Explore the dashboard:**
   - Jobs page - View job opportunities
   - Tasks page - Manage your tasks
   - Costs page - Monitor AI costs
   - Emails page - Email management

2. **Configure integrations:**
   - Add OpenClaw API key for AI features
   - Add Telegram bot for notifications
   - Add Gmail for email management

3. **Read documentation:**
   - `FIXES_COMPLETED.md` - What was fixed
   - `CRITICAL_GAPS_ANALYSIS.md` - System analysis
   - `backend/API_DOCUMENTATION.md` - API reference

4. **Test features:**
   - Create a task
   - View opportunities
   - Check system health
   - Monitor costs

---

## 💡 Pro Tips

1. **Keep terminals organized:**
   - Terminal 1: Backend
   - Terminal 2: Frontend
   - Terminal 3: Commands (migrations, docker, etc.)

2. **Use Docker Desktop GUI:**
   - View container logs
   - Restart containers
   - Monitor resource usage

3. **Check logs when debugging:**
   ```powershell
   # Backend logs
   # (shown in backend terminal)
   
   # Docker logs
   docker-compose logs -f postgres
   docker-compose logs -f redis
   
   # Frontend logs
   # (shown in frontend terminal)
   ```

4. **Bookmark useful URLs:**
   - Frontend: http://localhost:3000
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

---

## 🎯 Quick Reference

```powershell
# Start everything
docker-compose up -d postgres redis
cd backend && uvicorn app.main:app --reload  # Terminal 1
cd frontend && bun run dev                    # Terminal 2

# Stop everything
# Ctrl+C in both terminals
docker-compose down

# Check status
docker ps                    # Docker containers
curl http://localhost:8000/health  # Backend
# Open http://localhost:3000        # Frontend

# View logs
docker-compose logs -f postgres
docker-compose logs -f redis

# Reset database
docker-compose down -v
docker-compose up -d postgres redis
cd backend && alembic upgrade head
```

---

**Need help?** Check `QUICK_FIX_GUIDE.md` for detailed troubleshooting.

**Ready to deploy?** See `DEPLOYMENT_GUIDE.md` for production setup.

---

**Status:** ✅ Ready to use!  
**Version:** 3.1.0  
**Last Updated:** 2026-04-07

🚀 **Happy coding!**
