@echo off
echo ========================================
echo GRAXIA OS - START ALL SERVICES
echo ========================================
echo.
echo Starting Backend on port 8000...
echo.
start "Graxia Backend" cmd /k "cd /d C:\Users\menum\graxia os\backend && python -m uvicorn app.main:app --reload --port 8000"
echo.
echo Waiting 5 seconds for backend to start...
timeout /t 5 /nobreak >nul
echo.
echo Starting Frontend on port 5173...
echo.
start "Graxia Frontend" cmd /k "cd /d C:\Users\menum\graxia os\frontend && bun run dev"
echo.
echo ========================================
echo Services starting...
echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo API Docs: http://localhost:8000/docs
echo ========================================
echo.
pause
