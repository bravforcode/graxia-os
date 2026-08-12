# TASK 2.1 Deployment Guide: Required Secrets Validation

**Issue:** [H-01] Default Development Secrets in Configuration  
**Date:** 2026-05-07  
**Estimated Effort:** 1.5 hours  
**Breaking Change:** YES

---

## Executive Summary

This deployment enforces required secrets validation at application startup to prevent deployment with weak or placeholder credentials. The application will now refuse to start if `SECRET_KEY`, `ENCRYPTION_KEY`, or `POSTGRES_PASSWORD` are missing or appear to be placeholders (except in testing mode).

**Impact:** All developers and deployment environments must configure strong secrets before starting the application.

---

## Breaking Changes

### What Changed

1. **Default values removed:**
   - `SECRET_KEY`: Changed from `"development-secret-key-change-me"` to `None`
   - `ENCRYPTION_KEY`: Changed from `""` to `None`
   - `POSTGRES_PASSWORD`: Changed from `"changeme"` to `None`

2. **Startup validation added:**
   - Application validates secrets at startup (except in testing mode)
   - Rejects missing, empty, or placeholder-looking secrets
   - Enforces minimum length requirements:
     - `SECRET_KEY`: 32+ characters
     - `ENCRYPTION_KEY`: 32+ characters
     - `POSTGRES_PASSWORD`: 16+ characters
   - Validates `SECRET_KEY` entropy (minimum 4.0 bits)

3. **Testing mode exception:**
   - When `APP_ENV=testing`, auto-generates safe test defaults
   - Allows CI/CD pipelines to run without manual configuration

### Who Is Affected

- **Local developers:** Must configure secrets in `.env` before running the application
- **CI/CD pipelines:** Must set environment variables (or use `APP_ENV=testing`)
- **Staging/Production:** Must have strong secrets configured (already required, now enforced)

---

## Pre-Deployment Checklist

### 1. Generate Strong Secrets

Generate cryptographically strong secrets using OpenSSL:

```bash
# Generate SECRET_KEY (64 hex characters = 32 bytes)
openssl rand -hex 32

# Generate ENCRYPTION_KEY (64 hex characters = 32 bytes)
openssl rand -hex 32

# Generate POSTGRES_PASSWORD (base64 encoded, ~32 characters)
openssl rand -base64 32
```

**Example output:**
```
SECRET_KEY:        9f8e7d6c5b4a39281706152e1d0c9b8a7f6e5d4c3b2a19180f0e0d0c0b0a0908
ENCRYPTION_KEY:    1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b
POSTGRES_PASSWORD: Kx7mP9nQ2rS5tU8vW1xY4zA6bC9dE2fG3hI6jK9lM2nO5pQ8rS1tU4vW7xY0zA3b
```

### 2. Update Local Development Environment

**For each developer:**

1. Copy `.env.example` to `.env` (if not already done):
   ```bash
   cp .env.example .env
   ```

2. Add the generated secrets to `.env`:
   ```bash
   # Add to .env file
   SECRET_KEY=9f8e7d6c5b4a39281706152e1d0c9b8a7f6e5d4c3b2a19180f0e0d0c0b0a0908
   ENCRYPTION_KEY=1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b
   POSTGRES_PASSWORD=Kx7mP9nQ2rS5tU8vW1xY4zA6bC9dE2fG3hI6jK9lM2nO5pQ8rS1tU4vW7xY0zA3b
   ```

3. Update `DATABASE_URL` with the new password:
   ```bash
   DATABASE_URL=postgresql+asyncpg://graxia:Kx7mP9nQ2rS5tU8vW1xY4zA6bC9dE2fG3hI6jK9lM2nO5pQ8rS1tU4vW7xY0zA3b@localhost:5432/graxia_revenue_os
   ```

4. Verify the application starts:
   ```bash
   cd backend
   python -m app.main
   ```

   **Expected:** Application starts successfully  
   **If error:** Check that all three secrets are set and meet minimum length requirements

### 3. Update CI/CD Environment Variables

**For GitHub Actions / GitLab CI / Jenkins:**

Add the following environment variables to your CI/CD platform:

```bash
SECRET_KEY=<generated-secret-key>
ENCRYPTION_KEY=<generated-encryption-key>
POSTGRES_PASSWORD=<generated-postgres-password>
```

**Alternative for test pipelines:**

Set `APP_ENV=testing` to use auto-generated test defaults:

```yaml
# .github/workflows/test.yml
env:
  APP_ENV: testing
```

### 4. Update Staging Environment

**Before deployment:**

1. Generate production-grade secrets (different from development)
2. Add to staging environment variables
3. Update database connection string with new password
4. Restart database with new password (if needed)

**Deployment steps:**

```bash
# 1. Set environment variables in staging
export SECRET_KEY=<staging-secret-key>
export ENCRYPTION_KEY=<staging-encryption-key>
export POSTGRES_PASSWORD=<staging-postgres-password>

# 2. Update database password (if using managed database)
# Follow your database provider's password change procedure

# 3. Deploy new code
git pull origin main
docker compose up -d --build

# 4. Verify startup
docker compose logs backend | grep -i "secret"
# Should NOT see any errors about missing secrets
```

### 5. Update Production Environment

**CRITICAL: Use different secrets for production than staging/development**

**Before deployment:**

1. Generate production-specific secrets
2. Store in secure secret management system (AWS Secrets Manager, HashiCorp Vault, etc.)
3. Update production environment variables
4. Schedule maintenance window for database password change

**Deployment steps:**

```bash
# 1. Backup current configuration
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# 2. Set new environment variables
export SECRET_KEY=<production-secret-key>
export ENCRYPTION_KEY=<production-encryption-key>
export POSTGRES_PASSWORD=<production-postgres-password>

# 3. Update database password (coordinate with DBA)
# This may require downtime depending on your setup

# 4. Deploy new code (blue-green deployment recommended)
./deploy-production.sh

# 5. Verify startup
curl -f http://localhost:8000/health || echo "Health check failed"

# 6. Monitor logs for 15 minutes
tail -f /var/log/graxia/backend.log | grep -i "error\|secret"
```

---

## Migration Guide for Developers

### Quick Start (5 minutes)

```bash
# 1. Generate secrets
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# 2. Add to .env
cat >> .env << EOF
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EOF

# 3. Update DATABASE_URL in .env
# Replace 'changeme' with $POSTGRES_PASSWORD

# 4. Restart application
docker compose restart backend
```

### Detailed Steps

1. **Check current configuration:**
   ```bash
   grep -E "SECRET_KEY|ENCRYPTION_KEY|POSTGRES_PASSWORD" .env
   ```

2. **Generate new secrets:**
   ```bash
   echo "SECRET_KEY=$(openssl rand -hex 32)"
   echo "ENCRYPTION_KEY=$(openssl rand -hex 32)"
   echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
   ```

3. **Update .env file:**
   - Open `.env` in your editor
   - Replace or add the three secrets
   - Update `DATABASE_URL` with new `POSTGRES_PASSWORD`

4. **Update database password (if needed):**
   ```bash
   # If using Docker Compose
   docker compose down
   docker volume rm graxia_postgres_data  # WARNING: Deletes data
   docker compose up -d postgres
   
   # Or update password in running database
   docker compose exec postgres psql -U postgres -c "ALTER USER graxia PASSWORD 'new-password';"
   ```

5. **Test startup:**
   ```bash
   cd backend
   python -c "from app.config import settings; print('✓ Configuration valid')"
   ```

6. **Start application:**
   ```bash
   docker compose up -d
   docker compose logs -f backend
   ```

---

## Testing Instructions

### 1. Run Test Suite

```bash
cd backend
python -m pytest tests/test_config_validation.py -v
```

**Expected output:**
```
tests/test_config_validation.py::TestRequiredSecretsValidation::test_startup_without_secrets_fails_in_development PASSED
tests/test_config_validation.py::TestRequiredSecretsValidation::test_startup_with_placeholder_secrets_fails PASSED
tests/test_config_validation.py::TestRequiredSecretsValidation::test_startup_with_weak_secret_key_fails PASSED
tests/test_config_validation.py::TestRequiredSecretsValidation::test_startup_with_strong_secrets_succeeds PASSED
tests/test_config_validation.py::TestRequiredSecretsValidation::test_testing_mode_allows_defaults PASSED
...
======================== 30 passed in 2.5s ========================
```

### 2. Manual Verification

**Test 1: Missing secrets should fail**
```bash
cd backend
unset SECRET_KEY ENCRYPTION_KEY POSTGRES_PASSWORD
python -c "from app.config import Settings; Settings(APP_ENV='development')"
# Expected: RuntimeError with clear error message
```

**Test 2: Weak secrets should fail**
```bash
python -c "from app.config import Settings; Settings(APP_ENV='development', SECRET_KEY='short', ENCRYPTION_KEY='weak', POSTGRES_PASSWORD='bad')"
# Expected: RuntimeError about weak secrets
```

**Test 3: Strong secrets should succeed**
```bash
python -c "from app.config import Settings; s = Settings(APP_ENV='development', SECRET_KEY='a'*32, ENCRYPTION_KEY='b'*32, POSTGRES_PASSWORD='c'*16); print('✓ Valid')"
# Expected: ✓ Valid
```

**Test 4: Testing mode should allow defaults**
```bash
python -c "from app.config import Settings; s = Settings(APP_ENV='testing'); print('✓ Testing mode works')"
# Expected: ✓ Testing mode works
```

### 3. Run Verification Script

```bash
cd backend
python scripts/verify_secrets_validation.py
```

**Expected output:**
```
🔍 Verifying Secrets Validation (TASK 2.1)
==========================================

✓ Test 1: Missing secrets rejected in development
✓ Test 2: Missing secrets rejected in production
✓ Test 3: Weak secrets rejected
✓ Test 4: Strong secrets accepted
✓ Test 5: Testing mode allows defaults

==========================================
✅ All verification tests passed!
```

---

## Rollback Plan

If issues arise after deployment, follow these steps:

### Immediate Rollback (< 5 minutes)

```bash
# 1. Revert code changes
git revert <commit-hash>
git push origin main

# 2. Restore previous environment variables
cp .env.backup.<timestamp> .env

# 3. Restart application
docker compose restart backend

# 4. Verify
curl -f http://localhost:8000/health
```

### Partial Rollback (Keep validation, use temporary secrets)

```bash
# 1. Generate temporary secrets
export SECRET_KEY=$(openssl rand -hex 32)
export ENCRYPTION_KEY=$(openssl rand -hex 32)
export POSTGRES_PASSWORD=$(openssl rand -base64 32)

# 2. Restart with temporary secrets
docker compose restart backend

# 3. Plan proper secret generation for next deployment
```

---

## Troubleshooting

### Error: "Required secrets not configured"

**Cause:** One or more required secrets are missing or look like placeholders.

**Solution:**
1. Check `.env` file has all three secrets
2. Ensure secrets don't contain words like "changeme", "placeholder", etc.
3. Verify secrets meet minimum length requirements

```bash
# Check current values
grep -E "SECRET_KEY|ENCRYPTION_KEY|POSTGRES_PASSWORD" .env

# Generate new secrets
openssl rand -hex 32  # For SECRET_KEY and ENCRYPTION_KEY
openssl rand -base64 32  # For POSTGRES_PASSWORD
```

### Error: "Weak secrets detected: SECRET_KEY must be at least 32 characters"

**Cause:** Secret is too short.

**Solution:**
```bash
# Generate longer secret
openssl rand -hex 32  # Produces 64-character hex string
```

### Error: "SECRET_KEY has insufficient entropy"

**Cause:** Secret uses repeated characters (e.g., "aaaaaaaaaa...").

**Solution:**
```bash
# Use OpenSSL to generate high-entropy secret
openssl rand -hex 32
```

### Error: "Database connection failed"

**Cause:** `POSTGRES_PASSWORD` in `DATABASE_URL` doesn't match the one in database.

**Solution:**
```bash
# Update database password to match .env
docker compose exec postgres psql -U postgres -c "ALTER USER graxia PASSWORD 'your-new-password';"

# Or update DATABASE_URL to match database password
# Edit .env and change DATABASE_URL
```

### CI/CD Pipeline Failing

**Cause:** CI/CD environment doesn't have secrets configured.

**Solution 1 (Recommended for test pipelines):**
```yaml
# Set APP_ENV=testing in CI config
env:
  APP_ENV: testing
```

**Solution 2 (For integration tests):**
```yaml
# Add secrets to CI environment variables
env:
  SECRET_KEY: ${{ secrets.SECRET_KEY }}
  ENCRYPTION_KEY: ${{ secrets.ENCRYPTION_KEY }}
  POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
```

---

## Security Considerations

### Secret Storage

**DO:**
- ✅ Store secrets in environment variables
- ✅ Use secret management systems (AWS Secrets Manager, Vault)
- ✅ Rotate secrets regularly (every 90 days)
- ✅ Use different secrets for each environment
- ✅ Generate secrets using cryptographically secure methods

**DON'T:**
- ❌ Commit secrets to version control
- ❌ Share secrets via email or chat
- ❌ Use the same secrets across environments
- ❌ Use predictable or dictionary-based secrets
- ❌ Store secrets in application code

### Secret Rotation

**Recommended schedule:**
- Development: Every 90 days
- Staging: Every 60 days
- Production: Every 30 days

**Rotation procedure:**
1. Generate new secrets
2. Update environment variables
3. Restart application
4. Verify functionality
5. Revoke old secrets

---

## Monitoring and Alerts

### What to Monitor

1. **Startup failures:**
   ```bash
   # Check logs for secret validation errors
   docker compose logs backend | grep -i "secret"
   ```

2. **Configuration errors:**
   ```bash
   # Monitor application startup
   tail -f /var/log/graxia/backend.log | grep -i "RuntimeError"
   ```

3. **Health check failures:**
   ```bash
   # Monitor health endpoint
   watch -n 5 'curl -f http://localhost:8000/health'
   ```

### Recommended Alerts

Set up alerts for:
- Application startup failures
- Health check failures
- Configuration validation errors
- Repeated authentication failures (may indicate compromised secrets)

---

## Post-Deployment Verification

### 1. Verify Application Started

```bash
# Check application is running
docker compose ps backend
# Status should be "Up"

# Check logs for errors
docker compose logs backend | grep -i "error\|secret"
# Should see no errors
```

### 2. Verify Secrets Are Loaded

```bash
# Test configuration loading
docker compose exec backend python -c "from app.config import settings; print('✓ Secrets loaded')"
# Expected: ✓ Secrets loaded
```

### 3. Verify Authentication Works

```bash
# Test JWT signing (requires SECRET_KEY)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'
# Should return JWT token or authentication error (not configuration error)
```

### 4. Verify Database Connection

```bash
# Test database connection (requires POSTGRES_PASSWORD)
docker compose exec backend python -c "from app.database import engine; print('✓ Database connected')"
# Expected: ✓ Database connected
```

---

## Support and Escalation

### Getting Help

1. **Check this guide first** - Most issues are covered in Troubleshooting section
2. **Run verification script** - `python scripts/verify_secrets_validation.py`
3. **Check logs** - `docker compose logs backend`
4. **Contact team lead** - If issue persists after 30 minutes

### Escalation Path

1. **Developer** → Check this guide and troubleshooting section
2. **Team Lead** → Review configuration and logs
3. **DevOps Engineer** → Check infrastructure and secret management
4. **CTO** → Critical production issues only

---

## Appendix

### A. Secret Generation Commands

```bash
# SECRET_KEY (64 hex characters)
openssl rand -hex 32

# ENCRYPTION_KEY (64 hex characters)
openssl rand -hex 32

# POSTGRES_PASSWORD (base64, ~32 characters)
openssl rand -base64 32

# Alternative: Using Python
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### B. Environment Variable Templates

**Development (.env):**
```bash
APP_ENV=development
SECRET_KEY=<generated-secret-key>
ENCRYPTION_KEY=<generated-encryption-key>
POSTGRES_PASSWORD=<generated-postgres-password>
DATABASE_URL=postgresql+asyncpg://graxia:<POSTGRES_PASSWORD>@localhost:5432/graxia_revenue_os
```

**Testing (CI/CD):**
```bash
APP_ENV=testing
# No secrets needed - auto-generated
```

**Production:**
```bash
APP_ENV=production
SECRET_KEY=<production-secret-key>
ENCRYPTION_KEY=<production-encryption-key>
POSTGRES_PASSWORD=<production-postgres-password>
DATABASE_URL=postgresql+asyncpg://graxia:<POSTGRES_PASSWORD>@prod-db.example.com:5432/graxia_revenue_os
```

### C. Validation Rules Reference

| Secret | Min Length | Entropy | Placeholder Check |
|--------|-----------|---------|-------------------|
| SECRET_KEY | 32 chars | 4.0 bits | Yes |
| ENCRYPTION_KEY | 32 chars | N/A | Yes |
| POSTGRES_PASSWORD | 16 chars | N/A | Yes |

**Placeholder patterns detected:**
- Empty string or whitespace only
- Contains: "changeme", "change-me", "your_", "your-", "paste_"
- Contains: "development-secret", "replace", "placeholder"
- Contains: "example.com", "your-domain"

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-07 | 1.0 | Initial deployment guide for TASK 2.1 |

---

**Document Owner:** Backend Team  
**Last Updated:** 2026-05-07  
**Next Review:** 2026-06-07
