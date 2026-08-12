@echo off
title Ai Factory n8n
cd /d "%~dp0"
echo Starting n8n... (browser will open http://localhost:5678)
where npx >nul 2>nul || (echo ERROR: Node.js not found - install from nodejs.org & pause & exit /b 1)
npx --yes n8n@latest
pause
