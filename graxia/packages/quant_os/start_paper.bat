@echo off
echo Starting Gold Bot Paper Trading...
cd /d "C:\Users\menum\graxia os"
python graxia\packages\quant_os\gold_bot\run_paper.py --duration 1 --capital 49911.92 --risk 0.5 > graxia\packages\quant_os\logs\paper_output.log 2>&1
echo Exit code: %ERRORLEVEL%
