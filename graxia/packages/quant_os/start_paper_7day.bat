@echo off
cd /d "C:\Users\menum\graxia os"
echo [%date% %time%] Starting Gold Bot 7-day paper trading >> graxia\packages\quant_os\logs\paper_7day.log
python -u graxia\packages\quant_os\gold_bot\run_paper.py --duration 168 --capital 49911.92 --risk 0.5 >> graxia\packages\quant_os\logs\paper_7day.log 2>&1
echo [%date% %time%] Exit code: %ERRORLEVEL% >> graxia\packages\quant_os\logs\paper_7day.log
