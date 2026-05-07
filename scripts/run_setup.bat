@echo off
cd /d "C:\Users\menum\graxia os"

echo ========================================
echo GRAXIA OS SETUP
echo ========================================
echo.

REM Step 1: Create vault
echo [Step 1] Creating Obsidian Vault...
if not exist "C:\Users\menum\OneDrive\Documents\Gracia" mkdir "C:\Users\menum\OneDrive\Documents\Gracia"
if not exist "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain" mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain"
mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\00-Inbox" 2>nul
mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\01-Projects" 2>nul
mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\02-Areas" 2>nul
mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\03-Resources" 2>nul
mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\04-Archive" 2>nul
mkdir "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\90-System" 2>nul
echo OK - Vault created
echo.

REM Step 2: Clear cache
echo [Step 2] Clearing Python cache...
if exist "backend\app\__pycache__" rmdir /s /q "backend\app\__pycache__" 2>nul
if exist "backend\app\core\__pycache__" rmdir /s /q "backend\app\core\__pycache__" 2>nul
if exist "backend\app\integrations\__pycache__" rmdir /s /q "backend\app\integrations\__pycache__" 2>nul
echo OK - Cache cleared
echo.

REM Step 3: Run test
echo [Step 3] Running test...
python scripts\test_agent_system.py
echo.

echo ========================================
echo SETUP COMPLETE
echo ========================================
echo.
echo Next steps:
echo 1. Open Obsidian and select 'Gracia' vault
echo 2. Run backend: cd backend ^&^& python -m uvicorn app.main:app --reload
echo 3. Run frontend: cd frontend ^&^& bun run dev
echo.
pause
