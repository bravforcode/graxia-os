# ⚡ Quick Start Guide

เริ่มใช้งาน Personal OS ใน 5 นาที!

## 🎯 Prerequisites

- Docker & Docker Compose
- Text editor
- 5 minutes

## 🚀 Steps

### 1. Clone & Configure (2 min)

```bash
# Clone repository
git clone https://github.com/yourusername/personal-os.git
cd personal-os

# Copy environment template
cp .env.example .env

# Edit .env (ใส่ API keys ของคุณ)
nano .env
```

**ต้องมีอย่างน้อย:**
- `DATABASE_URL` (Supabase)
- `REDIS_URL` (Upstash)
- `OPENCLAW_API_KEY` หรือ `GEMINI_API_KEY`

### 2. Start Services (1 min)

```bash
# Start all services
docker-compose up -d

# Wait for services to be ready
docker-compose logs -f backend
# รอจนเห็น "Application startup complete"
```

### 3. Initialize Database (1 min)

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Verify
docker-compose exec backend alembic current
```

### 4. Verify (1 min)

```bash
# Health check
curl http://localhost:8000/health

# Should return:
# {"status": "ready", "service": "Personal OS v3"}

# Open API docs
open http://localhost:8000/docs

# Open frontend
open http://localhost:3000
```

### 5. Test (Optional)

```bash
# Create test opportunity
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Opportunity",
    "source": "manual",
    "url": "https://example.com",
    "description": "Testing the system"
  }'

# List opportunities
curl http://localhost:8000/api/v1/opportunities
```

## 🎉 Done!

ระบบพร้อมใช้งานแล้ว!

### Next Steps

1. **Configure Obsidian** (optional)
   - ดู [OBSIDIAN_INTEGRATION.md](OBSIDIAN_INTEGRATION.md)

2. **Set up Telegram** (optional)
   - เพิ่ม `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID` ใน `.env`
   - Restart: `docker-compose restart backend`

3. **Configure Google Workspace** (optional)
   - ดู [PRE_DEVELOPMENT_CHECKLIST.md](backend/PRE_DEVELOPMENT_CHECKLIST.md)

4. **Explore API**
   - เปิด http://localhost:8000/docs
   - ทดลองเรียก endpoints

5. **Read Documentation**
   - [README.md](README.md) - Overview
   - [SYSTEM_TESTING_GUIDE.md](SYSTEM_TESTING_GUIDE.md) - Testing
   - [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Production

## 🔧 Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose logs backend

# Common issues:
# 1. Port already in use → Change ports in docker-compose.yml
# 2. Database connection failed → Check DATABASE_URL
# 3. Redis connection failed → Check REDIS_URL
```

### Database migration failed

```bash
# Reset database
docker-compose down -v
docker-compose up -d
docker-compose exec backend alembic upgrade head
```

### API returns errors

```bash
# Check environment variables
docker-compose exec backend env | grep -E "DATABASE|REDIS|API"

# Restart services
docker-compose restart
```

## 📚 Learn More

- [Full Documentation](README.md)
- [API Reference](http://localhost:8000/docs)
- [Testing Guide](SYSTEM_TESTING_GUIDE.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)

## 💡 Tips

1. **Use Docker logs** - `docker-compose logs -f [service]`
2. **Check health** - `curl http://localhost:8000/health`
3. **Read API docs** - http://localhost:8000/docs
4. **Run tests** - `docker-compose exec backend pytest tests/ -v`
5. **Monitor costs** - Check `/api/v1/metrics/current-week`

## 🎯 Common Tasks

### View logs

```bash
docker-compose logs -f backend
docker-compose logs -f celery
docker-compose logs -f postgres
```

### Restart services

```bash
docker-compose restart backend
docker-compose restart celery
docker-compose restart
```

### Stop services

```bash
docker-compose down
```

### Update code

```bash
git pull
docker-compose build
docker-compose up -d
docker-compose exec backend alembic upgrade head
```

### Run tests

```bash
docker-compose exec backend pytest tests/ -v
```

### Access database

```bash
docker-compose exec postgres psql -U personal_os -d personal_os
```

### Access Redis

```bash
docker-compose exec redis redis-cli
```

---

**Happy coding! 🚀**
