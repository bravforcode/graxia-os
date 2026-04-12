# 🚨 Disaster Recovery Plan

## Overview

This document outlines the disaster recovery procedures for Personal OS v3.

**RTO (Recovery Time Objective):** < 1 hour  
**RPO (Recovery Point Objective):** < 1 hour  
**Last Updated:** 2024-01-15

---

## 1. Backup Strategy

### 1.1 Automated Backups

**Schedule:**
- Full database backup: Daily at 2:00 AM Bangkok time
- Retention: 30 days
- Storage: Local + S3 (optional)
- Compression: gzip
- Encryption: AES-256 (S3)

**Backup Script:**
```bash
python backend/scripts/backup_database.py
```

**Backup Location:**
- Local: `./backups/backup_YYYYMMDD_HHMMSS.sql.gz`
- S3: `s3://[BUCKET]/personal-os/backups/backup_YYYYMMDD_HHMMSS.sql.gz`

### 1.2 Backup Verification

**Automated Verification:**
- File integrity check (gzip decompression)
- PostgreSQL dump header validation
- File size validation (> 0 bytes)

**Manual Verification (Weekly):**
```bash
# List backups
python backend/scripts/restore_database.py --list

# Test restore to staging
python backend/scripts/restore_database.py --test
```

---

## 2. Disaster Scenarios

### 2.1 Database Corruption

**Symptoms:**
- Database connection errors
- Data inconsistency
- Query failures

**Recovery Steps:**
1. Stop all services
   ```bash
   docker-compose down
   ```

2. Restore from latest backup
   ```bash
   python backend/scripts/restore_database.py
   # Select latest backup
   # Type 'YES' to confirm
   ```

3. Verify data integrity
   ```bash
   docker-compose up -d postgres
   docker-compose exec postgres psql -U personal_os -d personal_os -c "SELECT COUNT(*) FROM opportunities;"
   ```

4. Restart services
   ```bash
   docker-compose up -d
   ```

5. Verify system health
   ```bash
   curl http://localhost:8000/health
   ```

**Estimated Recovery Time:** 15-30 minutes

---

### 2.2 Complete Data Loss

**Symptoms:**
- Database not accessible
- All data missing
- Backup files corrupted

**Recovery Steps:**
1. Check S3 backups (if configured)
   ```bash
   aws s3 ls s3://[BUCKET]/personal-os/backups/
   ```

2. Download latest backup from S3
   ```bash
   aws s3 cp s3://[BUCKET]/personal-os/backups/backup_YYYYMMDD_HHMMSS.sql.gz ./backups/
   ```

3. Restore from S3 backup
   ```bash
   python backend/scripts/restore_database.py
   ```

4. If S3 backups also corrupted:
   - Contact cloud provider support
   - Check for point-in-time recovery options
   - Restore from oldest available backup
   - Accept data loss for recent period

**Estimated Recovery Time:** 30-60 minutes

---

### 2.3 Server Failure

**Symptoms:**
- Server not responding
- SSH connection failed
- Services down

**Recovery Steps:**
1. Provision new server
   ```bash
   # Use same specifications
   # Ubuntu 22.04 LTS
   # 4GB RAM, 2 CPU, 50GB SSD
   ```

2. Install dependencies
   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose python3 python3-pip postgresql-client
   ```

3. Clone repository
   ```bash
   git clone https://github.com/yourusername/personal-os.git
   cd personal-os
   ```

4. Restore environment variables
   ```bash
   cp .env.backup .env
   # Or manually recreate .env from documentation
   ```

5. Download latest backup
   ```bash
   # From S3 or backup server
   aws s3 cp s3://[BUCKET]/personal-os/backups/backup_YYYYMMDD_HHMMSS.sql.gz ./backups/
   ```

6. Start services
   ```bash
   docker-compose up -d
   ```

7. Restore database
   ```bash
   python backend/scripts/restore_database.py
   ```

8. Verify system
   ```bash
   curl http://localhost:8000/health
   ```

**Estimated Recovery Time:** 45-60 minutes

---

### 2.4 Application Failure

**Symptoms:**
- API errors
- Agent failures
- Scheduler not running

**Recovery Steps:**
1. Check logs
   ```bash
   docker-compose logs -f backend
   docker-compose logs -f celery
   ```

2. Restart services
   ```bash
   docker-compose restart backend
   docker-compose restart celery
   ```

3. If restart fails, rebuild
   ```bash
   docker-compose down
   docker-compose build
   docker-compose up -d
   ```

4. Run migrations
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

5. Verify system
   ```bash
   curl http://localhost:8000/health
   ```

**Estimated Recovery Time:** 5-15 minutes

---

### 2.5 Redis Failure

**Symptoms:**
- Cache errors
- Celery task failures
- Rate limiting not working

**Recovery Steps:**
1. Restart Redis
   ```bash
   docker-compose restart redis
   ```

2. If data corruption, flush Redis
   ```bash
   docker-compose exec redis redis-cli FLUSHALL
   ```

3. Restart dependent services
   ```bash
   docker-compose restart backend celery
   ```

**Estimated Recovery Time:** 2-5 minutes

**Note:** Redis data is ephemeral (cache only), no backup needed

---

## 3. Recovery Procedures

### 3.1 Pre-Recovery Checklist

- [ ] Identify disaster type
- [ ] Assess data loss extent
- [ ] Notify stakeholders
- [ ] Document incident
- [ ] Prepare recovery environment

### 3.2 Recovery Steps

1. **Stop all services**
   ```bash
   docker-compose down
   ```

2. **Assess damage**
   - Check database connectivity
   - Check file system integrity
   - Check backup availability

3. **Restore from backup**
   ```bash
   python backend/scripts/restore_database.py
   ```

4. **Verify restoration**
   - Check table count
   - Check row counts
   - Check data integrity
   - Run sample queries

5. **Restart services**
   ```bash
   docker-compose up -d
   ```

6. **Verify system health**
   - Check API endpoints
   - Check scheduled tasks
   - Check agent execution
   - Check integrations

7. **Monitor for issues**
   - Watch logs for errors
   - Check metrics
   - Verify data consistency

### 3.3 Post-Recovery Checklist

- [ ] System fully operational
- [ ] All services running
- [ ] Data integrity verified
- [ ] Integrations working
- [ ] Scheduled tasks running
- [ ] Incident documented
- [ ] Root cause identified
- [ ] Prevention measures implemented

---

## 4. Backup Testing Schedule

### 4.1 Weekly Tests

**Every Monday 10:00 AM:**
- List available backups
- Verify latest backup integrity
- Check backup file sizes
- Verify S3 uploads (if configured)

```bash
python backend/scripts/backup_database.py --verify
```

### 4.2 Monthly Tests

**First Monday of each month:**
- Full restore test to staging environment
- Data integrity verification
- Performance testing
- Documentation review

```bash
# Restore to staging
export DATABASE_URL="postgresql://staging..."
python backend/scripts/restore_database.py

# Verify data
docker-compose exec postgres psql -U personal_os -d personal_os_staging -c "SELECT COUNT(*) FROM opportunities;"
```

### 4.3 Quarterly Tests

**Every 3 months:**
- Disaster recovery drill (full scenario)
- Server failure simulation
- Complete system rebuild
- Team training
- Documentation update

---

## 5. Contact Information

### 5.1 Emergency Contacts

**System Administrator:**
- Name: [Your Name]
- Email: [your.email@example.com]
- Phone: [+66-XXX-XXX-XXXX]
- Telegram: [@yourusername]

**Cloud Provider Support:**
- AWS Support: https://console.aws.amazon.com/support/
- Supabase Support: https://supabase.com/support
- Railway Support: https://railway.app/help

### 5.2 Service Providers

**Database (Supabase):**
- Dashboard: https://app.supabase.com
- Support: support@supabase.com
- Status: https://status.supabase.com

**Redis (Upstash):**
- Dashboard: https://console.upstash.com
- Support: support@upstash.com
- Status: https://status.upstash.com

**OpenClaw:**
- Dashboard: https://openclaw.ai/dashboard
- Support: support@openclaw.ai

---

## 6. Incident Response

### 6.1 Severity Levels

**Critical (P0):**
- Complete system down
- Data loss
- Security breach
- Response time: Immediate

**High (P1):**
- Major feature broken
- Performance degradation
- Partial data loss
- Response time: < 1 hour

**Medium (P2):**
- Minor feature broken
- Non-critical errors
- Response time: < 4 hours

**Low (P3):**
- Cosmetic issues
- Enhancement requests
- Response time: < 24 hours

### 6.2 Incident Log Template

```markdown
## Incident Report

**Date:** YYYY-MM-DD HH:MM
**Severity:** P0/P1/P2/P3
**Status:** Investigating/Resolved

### Summary
Brief description of the incident

### Timeline
- HH:MM - Incident detected
- HH:MM - Investigation started
- HH:MM - Root cause identified
- HH:MM - Fix applied
- HH:MM - System restored
- HH:MM - Incident resolved

### Impact
- Services affected
- Users affected
- Data loss (if any)
- Downtime duration

### Root Cause
Detailed explanation of what caused the incident

### Resolution
Steps taken to resolve the incident

### Prevention
Measures to prevent similar incidents

### Action Items
- [ ] Update documentation
- [ ] Implement monitoring
- [ ] Add tests
- [ ] Train team
```

---

## 7. Monitoring & Alerts

### 7.1 Critical Alerts

**Backup Failures:**
- Alert: Telegram + Email
- Trigger: Backup script fails
- Action: Investigate immediately

**Database Down:**
- Alert: Telegram + Email + SMS
- Trigger: Database connection fails
- Action: Restore from backup

**Disk Space Low:**
- Alert: Telegram
- Trigger: Disk usage > 90%
- Action: Clean up old backups

### 7.2 Alert Configuration

```yaml
# monitoring/alerts.yml
alerts:
  - name: backup_failed
    condition: backup.status == "failed"
    severity: critical
    channels: [telegram, email]
    
  - name: database_down
    condition: database.status == "down"
    severity: critical
    channels: [telegram, email, sms]
    
  - name: disk_space_low
    condition: disk.usage > 90
    severity: high
    channels: [telegram]
```

---

## 8. Documentation

### 8.1 Required Documentation

- [ ] System architecture diagram
- [ ] Network topology
- [ ] Service dependencies
- [ ] API documentation
- [ ] Runbook
- [ ] This disaster recovery plan

### 8.2 Documentation Location

- GitHub: https://github.com/yourusername/personal-os
- Confluence: [Your Confluence URL]
- Google Drive: [Your Drive URL]

---

## 9. Compliance

### 9.1 Data Retention

- Backups: 30 days
- Logs: 90 days
- Audit trails: 1 year
- Incident reports: 2 years

### 9.2 Security

- Backups encrypted at rest (AES-256)
- Backups encrypted in transit (TLS 1.3)
- Access control (IAM roles)
- Audit logging enabled

---

## 10. Review & Updates

**Review Schedule:**
- Monthly: Backup verification
- Quarterly: Full DR drill
- Annually: Plan review and update

**Last Review:** 2024-01-15  
**Next Review:** 2024-04-15  
**Plan Version:** 1.0

---

**Remember:** Practice makes perfect. Regular DR drills ensure smooth recovery when disaster strikes.

