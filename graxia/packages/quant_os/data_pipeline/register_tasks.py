"""Register Windows Scheduled Tasks for Data Pipeline"""
import subprocess
import sys
from pathlib import Path

py = sys.executable
base = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline")

tasks = [
    {
        "name": "QuantOS-DataPipeline-Full",
        "script": str(base / "pipeline.py"),
        "schedule": "daily",
        "time": "05:00",
        "desc": "Full data pipeline - all sources"
    },
    {
        "name": "QuantOS-MarketData",
        "script": str(base / "pipeline.py"),
        "schedule": "daily",
        "time": "06:00",
        "desc": "Market data refresh"
    },
    {
        "name": "QuantOS-NewsSentiment",
        "script": str(base / "pipeline.py"),
        "schedule": "daily",
        "time": "10:00",
        "desc": "News sentiment update"
    },
]

for t in tasks:
    cmd = f'schtasks /create /tn "{t["name"]}" /tr "\\"{py}\\" \\"{t["script"]}\\"" /sc {t["schedule"]} /st {t["time"]} /f'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"OK: {t['name']} -> {t['schedule']} at {t['time']}")
    else:
        print(f"FAIL: {t['name']}: {result.stderr[:80]}")

print("\nDone!")
