@echo off
echo ============================================
echo   GOLD BOT - Demo Trading Quick Start
echo ============================================
echo.

REM Check if MT5 is running
tasklist /FI "IMAGENAME eq terminal64.exe" 2>NUL | find /I "terminal64.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] MT5 terminal is not running!
    echo.
    echo Please:
    echo   1. Open MetaTrader 5
    echo   2. Login to your DEMO account
    echo   3. Make sure XAUUSD chart is visible
    echo   4. Run this script again
    echo.
    pause
    exit /b 1
)

echo [OK] MT5 terminal is running
echo.

REM Check Python
python --version >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed!
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Check MetaTrader5 package
python -c "import MetaTrader5" >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing MetaTrader5 package...
    pip install MetaTrader5
)

REM Check other dependencies
echo [INFO] Checking dependencies...
python -c "import pandas" >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing pandas...
    pip install pandas
)

python -c "import pandas_ta" >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing pandas_ta...
    pip install pandas_ta
)

echo.
echo [OK] All dependencies ready
echo.
echo ============================================
echo   Starting Demo Trading...
echo ============================================
echo.

REM Run the demo
cd /d "%~dp0..\..\..\.."
python graxia\packages\quant_os\gold_bot\run_demo.py

pause
