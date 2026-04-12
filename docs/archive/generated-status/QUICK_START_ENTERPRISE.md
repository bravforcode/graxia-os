# 🚀 Quick Start - Enterprise Edition

**Version:** 3.1.0 Enterprise  
**Status:** Production Ready  
**Time to Deploy:** 15 minutes

---

## Prerequisites

- Docker Desktop installed and running
- Python 3.11+ (for local development)
- Bun or Node.js 18+ (for frontend)
- PostgreSQL 15+ (or use Docker)
- Redis 7+ (or use Docker)

---

## 🎯 Quick Deploy (Recommended)

### Step 1: Clone and Configure (2 minutes)

```bash
# Navigate to project
cd "c:\brav os"

# Copy environment file
cp .env.example .env

# Edit .env with your API keys
# Required:
#   - OPENCLAW_API_KEY or GEMINI_API_KEY
#   - TELEGRAM_BOT_TOKEN (optional)
#   - SECRET_KEY (generate with: openssl rand -hex 32)
```

### Step 2: Start Services (3 minutes)

```bash
# Start all services with Docker Compose
docker-compose up -d

# Wait for services to be ready
timeout /t 30

# Check status
docker-compose ps
```

### Step 3: Run Migrations (2 minutes)

```bash
# Run database migrations
cd backend
alembic upgrade head
cd ..
```

### Step 4: Verify Deployment (3 minutes)

```bash
# Check backend health
curl http://localhost:8000/health

# Check frontend
curl http://localhost:3000

# Check metrics
curl http://localhost:8000/metrics

# Check event bus
curl http://localhost:8000/api/v1/events/stats
```

### Step 5: Create First User (2 minutes)

1. Open browser: http://localhost:3000
2. Click "Register"
3. Enter email and password
4. Click "Create account"
5. You're in! 🎉

---

## 🛠️ Manual Setup (Alternative)

### Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
bun install

# Start dev server
bun run dev
```

### Database (if not using Docker)

```bash
# Create database
createdb personal_os

# Update .env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/personal_os
```

### Redis (if not using Docker)

```bash
# Start Redis
redis-server

# Update .env
REDIS_URL=redis://localhost:6379/0
```

---

## ✅ Verification Checklist

### Services Running
- [ ] PostgreSQL: `docker ps | grep postgres`
- [ ] Redis: `docker ps | grep redis`
- [ ] Backend: `curl http://localhost:8000/health`
- [ ] Frontend: `curl http://localhost:3000`

### Features Working
- [ ] User registration
- [ ] User login
- [ ] Dashboard loads
- [ ] API responds
- [ ] Metrics available
- [ ] Event bus monitoring

### Enterprise Features
- [ ] Cost tracking: `curl http://localhost:8000/api/v1/costs/summary`
- [ ] Event monitoring: `curl http://localhost:8000/api/v1/events/stats`
- [ ] Health checks: `curl http://localhost:8000/health`
- [ ] Metrics: `curl http://localhost:8000/metrics`

---

## 🎯 Quick Tests

### Test Backend

```bash
cd backend
pytest tests/ -v
```

### Test API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# System status
curl http://localhost:8000/api/v1/system/status

# Event bus stats
curl http://localhost:8000/api/v1/events/stats

# Cost summary (requires auth)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/costs/summary
```

### Test Frontend

```bash
# Open in browser
start http://localhost:3000

# Or use curl
curl http://localhost:3000
```

---

## 🔧 Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# AI (choose one or both)
OPENCLAW_API_KEY=your_openclaw_key
GEMINI_API_KEY=your_gemini_key

# Auth
SECRET_KEY=your_secret_key_here

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_POLLING_ENABLED=false

# App
APP_ENV=production
LOG_LEVEL=INFO
```

### Optional Environment Variables

```bash
# Google Workspace
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token

# Obsidian
OBSIDIAN_VAULT_PATH=C:/path/to/vault

# Cost Limits
MAX_DAILY_AI_COST_USD=2.00
MAX_MONTHLY_AI_COST_USD=50.00
```

---

## 📊 Monitoring

### Health Endpoints

```bash
# Application health
curl http://localhost:8000/health

# System status
curl http://localhost:8000/api/v1/system/status

# Prometheus metrics
curl http://localhost:8000/metrics
```

### Event Bus Monitoring

```bash
# Event statistics
curl http://localhost:8000/api/v1/events/stats

# Failed events
curl http://localhost:8000/api/v1/events/failed

# Event handlers
curl http://localhost:8000/api/v1/events/handlers
```

### Cost Tracking

```bash
# Cost summary
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/v1/costs/summary

# Cost usage
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/v1/costs/usage?days=7

# Cost forecast
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/v1/costs/forecast
```

---

## 🐛 Troubleshooting

### Docker Issues

```bash
# Restart services
docker-compose restart

# View logs
docker-compose logs -f backend

# Rebuild
docker-compose build --no-cache
docker-compose up -d
```

### Database Issues

```bash
# Check connection
docker exec -it personal_os_postgres psql -U personal_os -d personal_os -c "SELECT 1;"

# Reset database
docker-compose down -v
docker-compose up -d postgres
cd backend && alembic upgrade head
```

### Backend Issues

```bash
# Check logs
tail -f backend/uvicorn-local.log

# Restart
docker-compose restart backend

# Check health
curl http://localhost:8000/health
```

### Frontend Issues

```bash
# Clear cache
cd frontend
rm -rf node_modules .next
bun install

# Restart
docker-compose restart frontend
```

---

## 📚 Documentation

### Essential Docs
- `DEPLOYMENT_CHECKLIST.md` - Full deployment guide
- `ENTERPRISE_READY_STATUS.md` - System status
- `FIXES_APPLIED.md` - Recent fixes
- `TROUBLESHOOTING_GUIDE.md` - Common issues

### API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

### Architecture
- `agent.md` - Agent system overview
- `backend/API_DOCUMENTATION.md` - API details
- `SYSTEM_STATUS.md` - System architecture

---

## 🎯 Next Steps

### After Deployment

1. **Create Admin User**
   - Register at http://localhost:3000/register
   - Use a strong password

2. **Configure Integrations**
   - Set up Telegram bot (optional)
   - Configure Google Workspace (optional)
   - Set up Obsidian sync (optional)

3. **Test Features**
   - Run job discovery
   - Check email processing
   - Test scrapers
   - Verify agents

4. **Monitor System**
   - Check logs daily
   - Review metrics weekly
   - Verify backups daily
   - Review costs weekly

### Production Deployment

1. **Security Hardening**
   - Change all default passwords
   - Enable HTTPS
   - Configure firewall
   - Set up SSL certificates

2. **Performance Tuning**
   - Adjust worker counts
   - Optimize database
   - Configure caching
   - Set up CDN

3. **Monitoring Setup**
   - Configure Grafana
   - Set up alerts
   - Enable logging
   - Configure backups

4. **Documentation**
   - Document custom configs
   - Create runbooks
   - Train team
   - Set up support

---

## 🚀 Production Checklist

### Before Going Live
- [ ] All tests passing
- [ ] Security hardened
- [ ] Backups configured
- [ ] Monitoring setup
- [ ] Documentation complete
- [ ] Team trained
- [ ] Disaster recovery tested
- [ ] Performance tested

### After Going Live
- [ ] Monitor 24/7 (first week)
- [ ] Check logs daily
- [ ] Review metrics weekly
- [ ] Verify backups daily
- [ ] Collect feedback
- [ ] Plan improvements

---

## 💡 Pro Tips

1. **Use Docker Compose** for easiest setup
2. **Enable backups** from day one
3. **Monitor costs** to stay within budget
4. **Check logs** regularly for issues
5. **Test backups** monthly
6. **Update dependencies** quarterly
7. **Review security** monthly
8. **Optimize performance** as needed

---

## 📞 Support

### Getting Help
- Check `TROUBLESHOOTING_GUIDE.md` first
- Review logs for errors
- Check health endpoints
- Verify configuration

### Resources
- Documentation: `/docs` directory
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

---

## 🎉 Success!

If you've completed all steps, you now have:

✅ Enterprise-grade system running  
✅ All features working  
✅ Monitoring enabled  
✅ Backups configured  
✅ Security hardened  
✅ Documentation complete  

**Congratulations! Your Personal Sovereign Enterprise OS is live!** 🚀

---

**Version:** 3.1.0 Enterprise  
**Status:** Production Ready  
**Last Updated:** 2026-04-07

*Happy automating!* 🤖

