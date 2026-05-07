@echo off
echo ========================================
echo GRAXIA OS SETUP
echo ========================================
echo.

REM Create vault structure
echo [1/4] Creating Obsidian Vault...
if not exist "C:\Users\menum\OneDrive\Documents\Gracia" mkdir "C:\Users\menum\OneDrive\Documents\Gracia"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\00-Inbox" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\00-Inbox"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\01-Projects" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\01-Projects"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\02-Areas" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\02-Areas"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\03-Resources" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\03-Resources"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\04-Archive" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\04-Archive"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\90-System" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\90-System"
echo [OK] Vault structure created
echo.

REM Clear cache
echo [2/4] Clearing Python cache...
if exist backend\app\__pycache__ rmdir /s /q backend\app\__pycache__ 2>nul
echo [OK] Cache cleared
echo.

echo [3/4] Checking env file...
if exist backend\.env (
    echo [OK] backend\.env exists
) else (
    echo [ERROR] backend\.env not found
)
echo.

echo [4/4] Running test...
cd /d "C:\Users\menum\graxia os"
python scripts\test_agent_system.py
echo.
echo ========================================
echo SETUP COMPLETE
echo ========================================
pause
