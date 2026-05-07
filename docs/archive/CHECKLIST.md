# ✅ Graxia OS Production Deployment Checklist

## Pre-Deployment

### Accounts Setup
- [ ] GitHub account ready
- [ ] Fly.io account created (verified)
- [ ] Supabase account created
- [ ] Upstash account created
- [ ] Vercel account ready

### Local Environment
- [ ] `.env` file created from `.env.flyio-template`
- [ ] All required secrets generated (SECRET_KEY, ENCRYPTION_KEY, INTERNAL_API_KEY)
- [ ] Database URLs use port 6543 (Supabase Transaction mode)
- [ ] Redis URL from Upstash is set

---

## Infrastructure Setup

### Supabase
- [ ] Project created (Singapore region)
- [ ] Database password saved
- [ ] Connection string for port 6543 copied
- [ ] Connection string for port 5432 copied (for migrations)
- [ ] Tables created (run migrations)

### Upstash
- [ ] Redis database created (Singapore)
- [ ] REDIS_URL copied
- [ ] QStash created (optional)
- [ ] QSTASH_TOKEN saved

### Fly.io
- [ ] `graxia-api` app created
- [ ] `graxia-worker` app created
- [ ] Secrets set for both apps
- [ ] fly.toml verified
- [ ] fly.worker.toml verified

---

## Deployment

### Backend API
- [ ] `flyctl deploy --config fly.toml` successful
- [ ] Health endpoint returns 200
- [ ] Database connection working
- [ ] Redis connection working

### Worker
- [ ] `flyctl deploy --config fly.worker.toml` successful
- [ ] Worker logs show "Connected to redis"
- [ ] Worker polling for jobs

### GitHub Actions
- [ ] Repository secrets set:
  - [ ] GRAXIA_API_URL
  - [ ] INTERNAL_API_KEY
  - [ ] FLY_API_TOKEN (optional, for auto-deploy)
- [ ] Workflows enabled in repo settings
- [ ] Test manual trigger of cron-lead-hunter.yml

---

## Frontend Integration

### Vercel
- [ ] vercel.json updated with Fly.io URL
- [ ] Frontend deployed
- [ ] API calls from frontend working
- [ ] CORS configured correctly

### Domain (Optional)
- [ ] Cloudflare DNS configured
- [ ] SSL certificate active
- [ ] Both frontend and API accessible via custom domain

---

## Testing

### API Tests
- [ ] GET /health returns 200
- [ ] GET /api/v1/system/health returns 200
- [ ] Authentication working (login/logout)
- [ ] Database queries working

### Worker Tests
- [ ] Manual trigger of lead hunter works
- [ ] Jobs appear in Redis queue
- [ ] Worker processes jobs
- [ ] Results saved to database

### Cron Tests
- [ ] GitHub Actions workflow triggered successfully
- [ ] Lead hunter runs every 15 minutes
- [ ] Daily report generated
- [ ] Logs visible in GitHub Actions

### End-to-End Tests
- [ ] Frontend loads without errors
- [ ] API health check from frontend works
- [ ] User can login
- [ ] Opportunities list loads
- [ ] Lead hunter trigger works from UI

---

## Security

- [ ] All placeholder secrets replaced
- [ ] SECRET_KEY >= 64 characters
- [ ] ENCRYPTION_KEY is valid Fernet key
- [ ] INTERNAL_API_KEY set and matches GitHub secret
- [ ] Redis passwords strong
- [ ] Telegram bot token valid
- [ ] CORS origins restricted to production domains
- [ ] No hardcoded credentials in code
- [ ] .env in .gitignore

---

## Monitoring

### Alerts Setup
- [ ] Telegram notifications working
- [ ] Error tracking (Sentry) configured (optional)
- [ ] Uptime monitoring (Better Stack) configured (optional)

### Logging
- [ ] Fly.io logs accessible
- [ ] Database logs in Supabase dashboard
- [ ] Redis logs in Upstash dashboard

---

## Documentation

- [ ] DEPLOYMENT_GUIDE.md reviewed
- [ ] Environment variables documented
- [ ] API endpoints documented
- [ ] Troubleshooting steps documented

---

## Post-Deployment

### First Hour
- [ ] Monitor Fly.io logs for errors
- [ ] Check database connections
- [ ] Verify worker is processing jobs
- [ ] Test all critical user flows

### First Day
- [ ] Monitor GitHub Actions runs
- [ ] Check Supabase storage usage
- [ ] Verify Upstash command usage
- [ ] Test cron jobs multiple times

### First Week
- [ ] Review all monitoring dashboards
- [ ] Check for any performance issues
- [ ] Monitor free tier limits
- [ ] Plan for scaling if needed

---

## Rollback Plan

If deployment fails:

1. **Immediate rollback:**
   ```bash
   flyctl deploy --app graxia-api --image <previous-image>
   ```

2. **Database issues:**
   - Check connection strings
   - Verify port 6543 is used (not 5432)
   - Check Supabase dashboard for errors

3. **Worker issues:**
   - Restart: `flyctl restart --app graxia-worker`
   - Check Redis connection
   - Verify secrets are set

4. **API issues:**
   - Check logs: `flyctl logs --app graxia-api`
   - Verify health endpoint
   - Redeploy if needed

---

## Sign-off

- [ ] All checklist items complete
- [ ] System tested and working
- [ ] Team notified of deployment
- [ ] Documentation updated

**Deployed by**: _______________  
**Date**: _______________  
**Version**: _______________

---

🎉 **Deployment Complete!**
