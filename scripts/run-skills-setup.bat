@echo off
REM Rebuild the file-based Universal Skills Hub.
REM Daily use does not require this script.

cd /d "%~dp0"

echo.
echo ========================================
echo Universal Skills Hub Reindex
echo ========================================
echo.

python scripts\consolidate_all_skills.py
if errorlevel 1 (
    echo Error during skills consolidation
    pause
    exit /b 1
)

echo.
python scripts\verify_skills_hub.py
if errorlevel 1 (
    echo Skills hub verification failed
    pause
    exit /b 1
)

echo.
echo Universal Skills Hub is ready. No background process is required.
echo.
pause
