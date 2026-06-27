@echo off
REM ═══════════════════════════════════════════════════════════════════
REM Quant OS — Windows Service Installation (NSSM)
REM
REM Requirements:
REM   - NSSM installed: https://nssm.cc/download
REM   - Python in PATH
REM
REM Usage:
REM   install_services.bat          # Install all services
REM   install_services.bat --remove # Remove all services
REM ═══════════════════════════════════════════════════════════════════

setlocal

set NSSM=nssm
set SERVICE_PREFIX=QuantOS
set PYTHON=%~dp0..\..\.venv\Scripts\python.exe
set SCRIPT_DIR=%~dp0

REM Check if Python exists
if not exist "%PYTHON%" (
    set PYTHON=python
)

REM Check NSSM
where %NSSM% >nul 2>&1
if errorlevel 1 (
    echo [ERROR] NSSM not found. Install from https://nssm.cc/download
    echo         Or add nssm.exe to PATH.
    exit /b 1
)

if "%1"=="--remove" goto :remove

echo ═══════════════════════════════════════════════════════════════
echo   Quant OS — Installing Services
echo ═══════════════════════════════════════════════════════════════

REM ─── Service 1: News Pipeline ───
echo [1/3] Installing %SERVICE_PREFIX%-NewsPipeline...
%NSSM% install %SERVICE_PREFIX%-NewsPipeline "%PYTHON%" "%SCRIPT_DIR%news_pipeline.py"
%NSSM% set %SERVICE_PREFIX%-NewsPipeline AppParameters "--loop --interval 300"
%NSSM% set %SERVICE_PREFIX%-NewsPipeline AppDirectory "%SCRIPT_DIR%.."
%NSSM% set %SERVICE_PREFIX%-NewsPipeline DisplayName "Quant OS — News Pipeline"
%NSSM% set %SERVICE_PREFIX%-NewsPipeline Description "Real-time news fetch + sentiment analysis → MacroRegimeCache"
%NSSM% set %SERVICE_PREFIX%-NewsPipeline Start SERVICE_AUTO_START
%NSSM% set %SERVICE_PREFIX%-NewsPipeline AppStdout "%SCRIPT_DIR%..\logs\news_pipeline.log"
%NSSM% set %SERVICE_PREFIX%-NewsPipeline AppStderr "%SCRIPT_DIR%..\logs\news_pipeline_err.log"
%NSSM% set %SERVICE_PREFIX%-NewsPipeline AppRotateFiles 1
%NSSM% set %SERVICE_PREFIX%-NewsPipeline AppRotateBytes 10485760
echo     Done.

REM ─── Service 2: Tier 3 Cron ───
echo [2/3] Installing %SERVICE_PREFIX%-Tier3Cron...
%NSSM% install %SERVICE_PREFIX%-Tier3Cron "%PYTHON%" "%SCRIPT_DIR%tier3_cron.py"
%NSSM% set %SERVICE_PREFIX%-Tier3Cron AppDirectory "%SCRIPT_DIR%.."
%NSSM% set %SERVICE_PREFIX%-Tier3Cron DisplayName "Quant OS — Tier 3 Cron"
%NSSM% set %SERVICE_PREFIX%-Tier3Cron Description "Gemini deep macro strategist (every 4 hours)"
%NSSM% set %SERVICE_PREFIX%-Tier3Cron Start SERVICE_AUTO_START
%NSSM% set %SERVICE_PREFIX%-Tier3Cron AppStdout "%SCRIPT_DIR%..\logs\tier3_cron.log"
%NSSM% set %SERVICE_PREFIX%-Tier3Cron AppStderr "%SCRIPT_DIR%..\logs\tier3_cron_err.log"
%NSSM% set %SERVICE_PREFIX%-Tier3Cron AppRotateFiles 1
%NSSM% set %SERVICE_PREFIX%-Tier3Cron AppRotateBytes 10485760
echo     Done.

REM ─── Service 3: Dashboard (manual start) ───
echo [3/3] Installing %SERVICE_PREFIX%-Dashboard...
%NSSM% install %SERVICE_PREFIX%-Dashboard "%PYTHON%" "%SCRIPT_DIR%dashboard.py"
%NSSM% set %SERVICE_PREFIX%-Dashboard AppDirectory "%SCRIPT_DIR%.."
%NSSM% set %SERVICE_PREFIX%-Dashboard DisplayName "Quant OS — Dashboard"
%NSSM% set %SERVICE_PREFIX%-Dashboard Description "MacroRegime monitoring dashboard"
%NSSM% set %SERVICE_PREFIX%-Dashboard Start SERVICE_DEMAND_START
%NSSM% set %SERVICE_PREFIX%-Dashboard AppStdout "%SCRIPT_DIR%..\logs\dashboard.log"
%NSSM% set %SERVICE_PREFIX%-Dashboard AppStderr "%SCRIPT_DIR%..\logs\dashboard_err.log"
echo     Done.

echo.
echo ═══════════════════════════════════════════════════════════════
echo   Services installed. Start with:
echo     net start %SERVICE_PREFIX%-NewsPipeline
echo     net start %SERVICE_PREFIX%-Tier3Cron
echo     net start %SERVICE_PREFIX%-Dashboard
echo ═══════════════════════════════════════════════════════════════
goto :eof

:remove
echo ═══════════════════════════════════════════════════════════════
echo   Quant OS — Removing Services
echo ═══════════════════════════════════════════════════════════════

%NSSM% stop %SERVICE_PREFIX%-NewsPipeline >nul 2>&1
%NSSM% remove %SERVICE_PREFIX%-NewsPipeline confirm
echo   Removed: %SERVICE_PREFIX%-NewsPipeline

%NSSM% stop %SERVICE_PREFIX%-Tier3Cron >nul 2>&1
%NSSM% remove %SERVICE_PREFIX%-Tier3Cron confirm
echo   Removed: %SERVICE_PREFIX%-Tier3Cron

%NSSM% stop %SERVICE_PREFIX%-Dashboard >nul 2>&1
%NSSM% remove %SERVICE_PREFIX%-Dashboard confirm
echo   Removed: %SERVICE_PREFIX%-Dashboard

echo.
echo   All services removed.
echo ═══════════════════════════════════════════════════════════════

endlocal
