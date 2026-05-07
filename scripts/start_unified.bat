@echo off
REM Graxia OS — Unified Startup (Windows)
REM Combines Revenue + Trading in one stack

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║  Graxia OS — Unified Platform (Revenue + Trading)                  ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

REM Check .env
if not exist ".env" (
    echo [ERROR] .env not found!
    echo Please run: copy .env.quant_os .env
    pause
    exit /b 1
)

REM Check Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not running!
    pause
    exit /b 1
)

echo [INFO] Starting optimized stack...
echo [INFO] Memory limit: ~800MB total
docker compose -f docker-compose.optimized.yml up -d

if errorlevel 1 (
    echo [ERROR] Failed to start
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Services starting...
timeout /t 10 /nobreak >nul

echo.
echo ═══════════════════════════════════════════════════════════════════
echo Services:
echo   API:      http://localhost:8000
echo   Docs:     http://localhost:8000/docs
echo.
echo Commands:
echo   Logs:    docker compose -f docker-compose.optimized.yml logs -f
echo   Stop:    docker compose -f docker-compose.optimized.yml down
echo   Status:  docker compose -f docker-compose.optimized.yml ps
echo.
echo [TRADING MODE: PAPER - Safe for testing]
echo.
pause
