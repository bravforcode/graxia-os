@echo off
echo Running setup as Administrator...
powershell -Command "Start-Process -FilePath 'powershell.exe' -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0setup_admin.ps1\"' -Verb RunAs -Wait"
echo Done!
pause
