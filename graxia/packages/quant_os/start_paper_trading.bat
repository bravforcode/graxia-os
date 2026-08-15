@echo off
REM Quant OS - Start Spread Measurement + Paper Trade Bot
REM Run this script to start both processes in background

set PYTHON=C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe
set GRAXIA_ROOT=C:\Users\menum\graxia os

echo Starting Quant OS processes...
echo.

REM Start Spread Measurement
echo Starting Spread Measurement...
start "QuantOS-Spread" /MIN "%PYTHON%" "%GRAXIA_ROOT%\graxia\packages\quant_os\scripts\measure_spread.py" --interval 60 --symbols XAUUSD,EURUSD,GBPUSD,BTCUSD
timeout /t 5 /nobreak >nul

REM Start Paper Trade Bot
echo Starting Paper Trade Bot...
start "QuantOS-Paper" /MIN "%PYTHON%" "%GRAXIA_ROOT%\graxia\packages\quant_os\scripts\paper_trade_bot.py"
timeout /t 5 /nobreak >nul

echo.
echo Both processes started!
echo   Spread Measurement: Running in background
echo   Paper Trade Bot: Running in background
echo.
echo To stop: taskkill /FI "WINDOWTITLE eq QuantOS-*" /F
echo.
pause
