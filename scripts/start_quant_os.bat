@echo off
REM ═══════════════════════════════════════════════════════════════════════════════
REM Quant OS — Windows Startup Script
REM Quick start for Windows users
REM ═══════════════════════════════════════════════════════════════════════════════

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║           Quant OS — Forex Trading System                          ║
echo ║           Windows Quick Start                                      ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

REM Check if .env exists
if not exist ".env" (
    echo [ERROR] .env file not found!
    echo.
    echo Please create .env file first:
    echo   copy .env.quant_os .env
    echo   edit .env and fill in your settings
    echo.
    pause
    exit /b 1
)

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop first.
    echo.
    pause
    exit /b 1
)

echo [INFO] Starting Quant OS services...
echo.

REM Create necessary directories
if not exist "logs" mkdir logs
if not exist "ml_models" mkdir ml_models

REM Start services
docker compose -f docker-compose.quant.yml up -d

if errorlevel 1 (
    echo [ERROR] Failed to start services!
    echo.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Quant OS is starting up!
echo.
echo Please wait for services to be ready...
timeout /t 10 /nobreak >nul

echo.
echo ═══════════════════════════════════════════════════════════════════
echo.
echo 📊 Services will be available at:
echo    API:        http://localhost:8000
echo    Grafana:    http://localhost:3001 (admin/admin)
echo    Prometheus: http://localhost:9091
echo.
echo 📋 Useful commands:
echo    View logs:   docker compose -f docker-compose.quant.yml logs -f
echo    Stop all:    docker compose -f docker-compose.quant.yml down
echo    Status:      docker compose -f docker-compose.quant.yml ps
echo.
echo 🔗 Telegram Bot Setup:
echo    1. Message @BotFather on Telegram
echo    2. Run: python scripts/setup_telegram_bot.py
echo.
echo ⚠️  TRADING MODE: PAPER (Safe for testing)
echo.
pause
