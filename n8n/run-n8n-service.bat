@echo off
cd /d "%~dp0"
set N8N_PORT=5678
set N8N_SECURE_COOKIE=false
set N8N_USER_FOLDER=%~dp0.n8n-data
REM Load secrets from .n8n-env (gitignored — keep keys out of git)
if exist "%~dp0.n8n-env" for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.n8n-env") do set "%%a=%%b"
if not defined ADMIN_EMAIL set ADMIN_EMAIL=admin@graxia.store
if not defined ADMIN_PASSWORD set ADMIN_PASSWORD=Graxia@Admin!2026
REM Run n8n directly from the npx cache (avoids re-download hangs)
set N8N_BIN=%~dp0..\..\AppData\Local\npm-cache\_npx\83f51bd5dfda7e85\node_modules\n8n\bin\n8n
if not exist "%N8N_BIN%" (
  npx --yes n8n@latest > "%~dp0n8n-run.log" 2>&1
) else (
  node "%N8N_BIN%" > "%~dp0n8n-run.log" 2>&1
)
