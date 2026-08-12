@echo off
cd /d "%~dp0"
set N8N_PORT=5678
set N8N_SECURE_COOKIE=false
set N8N_USER_FOLDER=%~dp0.n8n-data
REM Secrets come from .env.production (loaded by n8n via N8N env) or set here:
if not defined ADMIN_EMAIL set ADMIN_EMAIL=admin@graxia.store
if not defined ADMIN_PASSWORD set ADMIN_PASSWORD=Graxia@Admin!2026
REM INTERNAL_API_KEY and RESEND_API_KEY must be set in the environment
REM (or add them here as: set RESEND_API_KEY=re_xxx  set INTERNAL_API_KEY=xxx)
npx --yes n8n@latest > "%~dp0n8n-run.log" 2>&1
