# Deployment Guide - Personal OS v3

Complete guide for deploying Personal OS to production.

## Prerequisites

- Docker & Docker Compose
- PostgreSQL 15+
- Python 3.11+
- Node.js 18+
- Domain name with SSL certificate
- Cloud storage (AWS S3 or compatible)

## Environment Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd personal-os-v3
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required variables:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/personal_os

# API Keys
GEMINI_API_KEY=your_gemini_key
OPENCLAW_API_KEY=your_openclaw_key

# Security
SECRET_KEY=your-secret-key-min-32-chars
JWT_SECRET_KEY=your-jwt-secret-key
ENCRYPTION_KEY=your-encryption-key

# Google Workspace
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token

# Backup
BACKUP_S3_BUCKET=your-backup-bucket
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret

# Monitoring
SENTRY_DSN=your_sentry_dsn (optional)
```

## Deployment Options

### Option 1: Docker Compose (Recommended)

#### 1. Build Images

```bash
docker-compose build
```

#### 2. Start Services

```bash
docker-compose up -d
```

#### 3. Run Migrations

```bash
docker-compose exec backend alembic upgrade head
```

#### 4. Verify Health

```bash
curl http://localhost:8000/api/v1/system/health
```

### Option 2: Manual Deployment

#### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Serve with nginx or similar
```

## Database Setup

### 1. Create Database

```sql
CREATE DATABASE personal_os;
CREATE USER personal_os_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE personal_os TO personal_os_user;
```

### 2. Run Migrations

```bash
cd backend
alembic upgrade head
```

### 3. Verify Schema

```bash
psql -U personal_os_user -d personal_os -c "\dt"
```

## SSL/TLS Configuration

### Using Let's Encrypt with Nginx

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Frontend
    location / {
        root /var/www/personal-os/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Backup Configuration

### 1. Setup S3 Bucket

```bash
aws s3 mb s3://personal-os-backups
aws s3api put-bucket-versioning \
    --bucket personal-os-backups \
    --versioning-configuration Status=Enabled
```

### 2. Configure Backup Schedule

Backups run automatically at 2 AM daily via scheduler.

Manual backup:

```bash
python backend/backup_database.py
```

### 3. Test Restore

```bash
python backend/restore_database.py
```

## Monitoring Setup

### 1. Prometheus Configuration

Create `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'personal-os'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/v1/metrics'
```

### 2. Grafana Dashboards

Import dashboard from `monitoring/grafana/system.json`

### 3. Alert Rules

Configure alerts in `monitoring/alerts.yml`

## Security Hardening

### 1. Firewall Rules

```bash
# Allow SSH
ufw allow 22/tcp

# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Enable firewall
ufw enable
```

### 2. Rate Limiting

Configure in `backend/app/middleware/rate_limit.py`:

```python
RATE_LIMITS = {
    "default": "100/minute",
    "auth": "5/minute",
    "api": "1000/hour"
}
```

### 3. Security Headers

Already configured in `backend/app/middleware/security.py`

## Performance Optimization

### 1. Database Indexing

```sql
CREATE INDEX idx_opportunities_status ON opportunities(status);
CREATE INDEX idx_opportunities_score ON opportunities(total_score DESC);
CREATE INDEX idx_jobs_platform ON job_postings(source_platform);
CREATE INDEX idx_email_threads_status ON email_threads(status);
```

### 2. Connection Pooling

Configure in `backend/app/database.py`:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)
```

### 3. Caching

Enable Redis caching (optional):

```bash
docker run -d -p 6379:6379 redis:alpine
```

## Health Checks

### System Health

```bash
curl http://localhost:8000/api/v1/system/health
```

Expected response:

```json
{
  "status": "ok",
  "llm_degraded": false,
  "llm_cost_paused": false,
  "gemini_calls_today": 42,
  "event_stats": {}
}
```

### Database Health

```bash
curl http://localhost:8000/api/v1/system/health/db
```

### Scheduler Health

```bash
curl http://localhost:8000/api/v1/system/health/scheduler
```

## Troubleshooting

See [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md) for common issues.

## Rollback Procedure

### 1. Stop Services

```bash
docker-compose down
```

### 2. Restore Database

```bash
python backend/restore_database.py
```

### 3. Rollback Code

```bash
git checkout <previous-version-tag>
docker-compose build
docker-compose up -d
```

## Maintenance

### Daily Tasks

- Monitor logs: `docker-compose logs -f`
- Check disk space: `df -h`
- Verify backups: `ls -lh backups/`

### Weekly Tasks

- Review metrics dashboard
- Check error rates
- Update dependencies (if needed)

### Monthly Tasks

- Security audit
- Performance review
- Cost analysis

## Support

For issues or questions:
- Check logs: `docker-compose logs backend`
- Review [TROUBLESHOOTING_GUIDE.md](TROUBLESHOOTING_GUIDE.md)
- Check system health endpoints

## Production Checklist

- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] SSL certificates installed
- [ ] Backups configured and tested
- [ ] Monitoring setup complete
- [ ] Security headers enabled
- [ ] Rate limiting configured
- [ ] Firewall rules applied
- [ ] Health checks passing
- [ ] Documentation reviewed
