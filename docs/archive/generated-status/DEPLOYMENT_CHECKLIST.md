# 🚀 Production Deployment Checklist

**System:** Personal OS v3 Enterprise  
**Target:** Production Environment  
**Date:** 2026-04-07

---

## ✅ Pre-Deployment Checklist

### 1. Environment Configuration

- [ ] **Copy `.env.example` to `.env`**
  ```bash
  cp .env.example .env
  ```

- [ ] **Configure Database**
  ```bash
  # Option A: Local PostgreSQL
  DATABASE_URL=postgresql+asyncpg://personal_os:STRONG_PASSWORD@localhost:5432/personal_os
  
  # Option B: Supabase
  DATABASE_URL=postgresql+asyncpg://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
  ```

- [ ] **Configure Redis**
  ```bash
  REDIS_URL=redis://localhost:6379/0
  CELERY_BROKER_URL=redis://localhost:6379/1
  CELERY_RESULT_BACKEND=redis://localhost:6379/2
  ```

- [ ] **Configure AI APIs**
  ```bash
  # OpenClaw (Primary)
  OPENCLAW_API_KEY=your_real_api_key_here
  OPENCLAW_BASE_URL=https://api.openclaw.ai/v1
  
  # Gemini (Fallback)
  GEMINI_API_KEY=your_real_gemini_key_here
  ```

- [ ] **Configure Telegram**
  ```bash
  TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
  TELEGRAM_CHAT_ID=your_chat_id_from_userinfobot
  TELEGRAM_POLLING_ENABLED=true
  ```

- [ ] **Configure Google Workspace**
  ```bash
  GOOGLE_CLIENT_ID=your_client_id
  GOOGLE_CLIENT_SECRET=your_client_secret
  GOOGLE_REFRESH_TOKEN=your_refresh_token
  GOOGLE_WORKSPACE_EMAIL=you@example.com
  ```

- [ ] **Configure Obsidian**
  ```bash
  OBSIDIAN_VAULT_PATH=C:/path/to/your/vault
  OBSIDIAN_API_URL=http://localhost:27123  # Optional
  OBSIDIAN_API_KEY=your_api_key  # Optional
  ```

- [ ] **Generate Secret Key**
  ```bash
  # Generate a secure secret key
  openssl rand -hex 32
  # Add to .env
  SECRET_KEY=your_generated_secret_key_here
  ```

---

### 2. Infrastructure Setup

- [ ] **Start Docker Desktop** (Windows)
  - Open Docker Desktop application
  - Wait for it to fully start

- [ ] **Start Services**
  ```bash
  # Start PostgreSQL and Redis
  docker-compose up -d postgres redis
  
  # Verify services are running
  docker ps
  ```

- [ ] **Run Database Migrations**
  ```bash
  cd backend
  alembic upgrade head
  
  # Verify migrations
  alembic current
  # Should show: 007 (head)
  ```

- [ ] **Test Database Connection**
  ```bash
  # Test connection
  python -c "from app.database import engine; import asyncio; asyncio.run(engine.connect())"
  # Should not error
  ```

---

### 3. Backend Deployment

- [ ] **Install Dependencies**
  ```bash
  cd backend
  pip install -r requirements.txt
  ```

- [ ] **Test Backend Startup**
  ```bash
  # Start backend (test mode)
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  
  # Should see:
  # INFO:     Uvicorn running on http://0.0.0.0:8000
  # INFO:     Application startup complete
  ```

- [ ] **Test Health Endpoint**
  ```bash
  curl http://localhost:8000/health
  # Should return: {"status":"ok",...}
  ```

- [ ] **Test API Documentation**
  - Open: http://localhost:8000/docs
  - Should see Swagger UI

- [ ] **Start Celery Worker**
  ```bash
  # New terminal
  cd backend
  celery -A app.tasks.celery_app worker --loglevel=info
  
  # Should see:
  # [tasks]
  #   . app.tasks.morning_briefing
  #   . app.tasks.job_discovery
  #   ...
  ```

---

### 4. Frontend Deployment

- [ ] **Install Dependencies**
  ```bash
  cd frontend
  bun install
  ```

- [ ] **Configure API URL**
  ```bash
  # In .env or vite config
  VITE_API_BASE_URL=http://localhost:8000
  ```

- [ ] **Build Frontend**
  ```bash
  bun run build
  
  # Should create dist/ folder
  ```

- [ ] **Test Frontend**
  ```bash
  bun run dev
  
  # Should see:
  # VITE ready in XXX ms
  # Local: http://localhost:3000
  ```

- [ ] **Test Frontend Access**
  - Open: http://localhost:3000
  - Should redirect to /login

---

### 5. Authentication Setup

- [ ] **Create First User**
  - Go to: http://localhost:3000/register
  - Email: admin@example.com
  - Password: (strong password)
  - Click "Create account"

- [ ] **Test Login**
  - Go to: http://localhost:3000/login
  - Enter credentials
  - Should redirect to dashboard

- [ ] **Test Protected Routes**
  - Try accessing /opportunities
  - Should work (not redirect to login)

- [ ] **Test Logout**
  - Click logout
  - Should redirect to /login
  - Try accessing /opportunities
  - Should redirect to /login

---

### 6. Feature Testing

- [ ] **Test Opportunities**
  - Go to /opportunities
  - Should load (may be empty)
  - No errors in console

- [ ] **Test Jobs**
  - Go to /jobs
  - Should load
  - No errors

- [ ] **Test Contacts**
  - Go to /contacts
  - Should load
  - No errors

- [ ] **Test Email Threads**
  - Go to /emails
  - Should load
  - No errors

- [ ] **Test Tasks**
  - Go to /tasks
  - Should load
  - No errors

- [ ] **Test Costs**
  - Go to /costs
  - Should load
  - May show $0.00 (normal)

- [ ] **Test Event Bus**
  - Go to /event-bus
  - Should show health status
  - Should show "No failed events"

- [ ] **Test Metrics**
  - Go to /metrics
  - Should load
  - No errors

- [ ] **Test Drafts**
  - Go to /drafts
  - Should load
  - No errors

---

### 7. Integration Testing

- [ ] **Test Telegram Bot**
  ```bash
  # Send message to your bot
  /start
  
  # Should receive welcome message
  ```

- [ ] **Test Scheduled Jobs**
  ```bash
  # Check scheduler logs
  # Should see jobs scheduled:
  # - Morning briefing (8:00 AM)
  # - Job discovery (10:00 AM, 6:00 PM)
  # - Email processing (every 30 min)
  # - Daily scan (7:00 AM)
  # - Weekly strategy (Sunday 8:30 AM)
  ```

- [ ] **Test Scraper**
  ```bash
  # Manually trigger a scraper
  curl -X POST http://localhost:8000/api/v1/scrapers/run/linkedin
  
  # Check scraper health
  curl http://localhost:8000/api/v1/scrapers/health
  ```

- [ ] **Test Cost Tracking**
  ```bash
  # Check costs
  curl http://localhost:8000/api/v1/costs/summary
  
  # Should return cost data
  ```

- [ ] **Test Event Bus**
  ```bash
  # Check event stats
  curl http://localhost:8000/api/v1/events/stats
  
  # Should return event counts
  ```

---

### 8. Monitoring Setup

- [ ] **Test Prometheus Metrics**
  ```bash
  curl http://localhost:8000/metrics
  
  # Should return Prometheus format metrics
  ```

- [ ] **Test Health Checks**
  ```bash
  curl http://localhost:8000/health
  curl http://localhost:8000/api/v1/system/status
  
  # Both should return healthy status
  ```

- [ ] **Check Logs**
  ```bash
  # Backend logs
  tail -f backend/logs/app.log
  
  # Should see structured JSON logs
  ```

---

### 9. Security Verification

- [ ] **Test Rate Limiting**
  ```bash
  # Make 100+ requests quickly
  for i in {1..150}; do curl http://localhost:8000/health; done
  
  # Should get 429 Too Many Requests after limit
  ```

- [ ] **Test Auth Middleware**
  ```bash
  # Try accessing protected endpoint without token
  curl http://localhost:8000/api/v1/opportunities
  
  # Should get 401 Unauthorized
  ```

- [ ] **Test CORS**
  ```bash
  # Check CORS headers
  curl -H "Origin: http://localhost:3000" -I http://localhost:8000/health
  
  # Should have Access-Control-Allow-Origin header
  ```

- [ ] **Test Security Headers**
  ```bash
  curl -I http://localhost:8000/health
  
  # Should have:
  # X-Content-Type-Options: nosniff
  # X-Frame-Options: DENY
  # X-XSS-Protection: 1; mode=block
  ```

---

### 10. Backup & Recovery

- [ ] **Test Backup Script**
  ```bash
  cd backend
  python scripts/backup_database.py
  
  # Should create backup in backups/
  ```

- [ ] **Verify Backup File**
  ```bash
  ls -lh backend/backups/
  
  # Should see .sql.gz file
  ```

- [ ] **Test Restore Script**
  ```bash
  # DON'T run in production!
  # Test in dev environment only
  python scripts/restore_database.py
  ```

---

### 11. Performance Testing

- [ ] **Test API Response Times**
  ```bash
  # Use Apache Bench
  ab -n 100 -c 10 http://localhost:8000/health
  
  # Should be < 200ms average
  ```

- [ ] **Test Database Query Performance**
  ```bash
  # Check slow queries
  # Should be < 1 second
  ```

- [ ] **Test Frontend Load Time**
  - Open DevTools → Network
  - Reload page
  - Should load < 3 seconds

---

### 12. Final Checks

- [ ] **Review Logs**
  - No ERROR messages
  - No WARNING messages (except expected)
  - All services started successfully

- [ ] **Review Metrics**
  - CPU usage < 50%
  - Memory usage < 80%
  - Disk usage < 80%

- [ ] **Review Costs**
  - Daily cost < $2
  - Monthly forecast < $50

- [ ] **Review Documentation**
  - README.md up to date
  - API_DOCUMENTATION.md accurate
  - DEPLOYMENT_GUIDE.md complete

---

## 🚀 Go Live

### Production Deployment

- [ ] **Set Environment to Production**
  ```bash
  APP_ENV=production
  LOG_LEVEL=INFO
  ```

- [ ] **Disable Debug Mode**
  ```bash
  # In FastAPI
  # app = FastAPI(debug=False)
  ```

- [ ] **Start All Services**
  ```bash
  # Start everything
  docker-compose up -d
  
  # Verify all running
  docker ps
  ```

- [ ] **Monitor for 1 Hour**
  - Watch logs
  - Check metrics
  - Test all features
  - Monitor costs

- [ ] **Monitor for 24 Hours**
  - Check daily backup ran
  - Check scheduled jobs ran
  - Check no errors
  - Check costs within budget

---

## 📊 Success Criteria

### Must Have (Before Go-Live)
- ✅ All services start without errors
- ✅ Database migrations complete
- ✅ Authentication working
- ✅ All API endpoints responding
- ✅ Frontend loads and works
- ✅ No critical errors in logs

### Should Have (Week 1)
- ✅ Telegram bot working
- ✅ Scheduled jobs running
- ✅ Scrapers working
- ✅ Cost tracking accurate
- ✅ Backups running daily

### Nice to Have (Month 1)
- ✅ All integrations working
- ✅ Performance optimized
- ✅ Monitoring dashboards setup
- ✅ Documentation complete

---

## 🆘 Rollback Plan

If something goes wrong:

1. **Stop all services**
   ```bash
   docker-compose down
   ```

2. **Restore from backup**
   ```bash
   python scripts/restore_database.py
   ```

3. **Check logs**
   ```bash
   docker-compose logs -f
   ```

4. **Fix issue**

5. **Restart services**
   ```bash
   docker-compose up -d
   ```

---

## 📞 Support

**Issues?**
1. Check logs: `docker-compose logs -f`
2. Check health: `curl http://localhost:8000/health`
3. Check event bus: http://localhost:3000/event-bus
4. Review TROUBLESHOOTING_GUIDE.md

---

**Status:** Ready for Production ✅  
**Last Updated:** 2026-04-07  
**Version:** 3.0.0 Enterprise

**🚀 Good luck with deployment!**
