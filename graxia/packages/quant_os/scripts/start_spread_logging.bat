@echo off
REM Start spread logging as a background process
REM Logs to data\spread_log.jsonl
REM Stop with: taskkill /F /IM python.exe /FI "WINDOWTITLE eq measure_spread*"

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

echo ============================================
echo  SPREAD LOGGER — Pepperstone MT5
echo ============================================
echo  Symbols: XAUUSD EURUSD GBPUSD USDJPY BTCUSD ETHUSD XAGUSD(SILVER) SpotCrude(OIL)
echo  Interval: 60 seconds
echo  Output:   %PROJECT_DIR%\data\spread_log.jsonl
echo  Stop:     Ctrl+C or close this window
echo ============================================
echo.

python "%SCRIPT_DIR%measure_spread.py" --interval 60

pause
