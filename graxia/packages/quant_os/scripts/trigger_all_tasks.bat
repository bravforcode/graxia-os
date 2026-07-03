@echo off
echo ========================================
echo   GRAXIA TASK TRIGGER TEST
echo ========================================
echo.

echo 1. Triggering Graxia-Bridge-Sync...
schtasks /Run /TN "Graxia-Bridge-Sync" 2>nul
timeout /t 3 /nobreak >nul

echo 2. Triggering Graxia-Bridge-Upgrade...
schtasks /Run /TN "Graxia-Bridge-Upgrade" 2>nul
timeout /t 3 /nobreak >nul

echo 3. Triggering Graxia-Bridge-Upgrade-Quick...
schtasks /Run /TN "Graxia-Bridge-Upgrade-Quick" 2>nul
timeout /t 3 /nobreak >nul

echo 4. Triggering Graxia-Bridge-Daily...
schtasks /Run /TN "Graxia-Bridge-Daily" 2>nul
timeout /t 3 /nobreak >nul

echo 5. Triggering Graxia-Bridge-Research...
schtasks /Run /TN "Graxia-Bridge-Research" 2>nul
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo   CHECKING STATUS...
echo ========================================
schtasks /Query /TN "Graxia-Bridge*" /FO TABLE
echo.
echo Done!
pause
