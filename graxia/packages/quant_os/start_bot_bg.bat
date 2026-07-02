@echo off
cd /d "C:\Users\menum\graxia os"
echo Starting Gold Bot Paper Trading...
python -u graxia\packages\quant_os\gold_bot\run_paper.py --duration 168 --capital 49911.92 --risk 0.25 > graxia\packages\quant_os\logs\paper_7day.log 2> graxia\packages\quant_os\logs\paper_7day_err.log
