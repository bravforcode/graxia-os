@echo off
REM GRAXIA-OS Paper Trade Bot - Windows Startup Script
REM Runs the bot in background every 60 seconds on M15 XAUUSD
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
start /B python -u scripts/paper_trade_bot.py --interval 15 >> data/bot_out.log 2>> data/bot_err.log
echo Bot started at %date% %time%
