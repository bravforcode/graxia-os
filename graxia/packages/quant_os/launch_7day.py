"""Launch 7-day paper trading as a permanent background process.

Entry point: scripts/tsm_paper_trade.py (multi-asset TSM paper bot)
Replaces: gold_bot/run_paper.py (removed, gold-only prototype)
"""

import subprocess
import sys
import os

os.chdir(r"C:\Users\menum\graxia os")

log = os.path.abspath(r"graxia\packages\quant_os\logs\paper_7day.log")
err = os.path.abspath(r"graxia\packages\quant_os\logs\paper_7day_err.log")
os.makedirs(os.path.dirname(log), exist_ok=True)

print("Launching multi-asset TSM paper trading...")
print(f"  Entry: scripts/tsm_paper_trade.py")
print(f"  Log: {log}")

proc = subprocess.Popen(
    [
        sys.executable, "-u",
        r"graxia\packages\quant_os\scripts\tsm_paper_trade.py",
        "--duration", "168",
        "--capital", "49911.92",
        "--risk", "0.25",
    ],
    cwd=r"C:\Users\menum\graxia os",
    stdout=open(log, "w"),
    stderr=open(err, "w"),
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
    close_fds=True,
)

with open(r"graxia\packages\quant_os\logs\paper_7day.pid", "w") as f:
    f.write(str(proc.pid))

print(f"  PID: {proc.pid}")
print(f"  Log: {log}")
print(f"  Stop: taskkill /PID {proc.pid} /F")
