@echo off
title GRAXIA-OS Paper Trade Bot v2.0
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\menum\graxia os\graxia\packages\quant_os"
"C:\Users\menum\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" -u scripts/paper_trade_bot.py --interval 15
