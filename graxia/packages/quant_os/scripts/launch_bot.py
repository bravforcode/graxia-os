"""Launcher for paper trade bot - handles logging properly."""
import os
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PYTHON = r"C:\Users\menum\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
BOT = BASE / "scripts" / "paper_trade_bot.py"
OUT_LOG = BASE / "data" / "bot_out.log"
ERR_LOG = BASE / "data" / "bot_err.log"

# Clear old logs
OUT_LOG.write_text("", encoding="utf-8")
ERR_LOG.write_text("", encoding="utf-8")

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

print(f"Starting bot: {BOT}")
print(f"Output: {OUT_LOG}")
print(f"Errors: {ERR_LOG}")

proc = subprocess.Popen(
    [PYTHON, "-u", str(BOT), "--interval", "15"],
    cwd=str(BASE),
    env=env,
    stdout=open(OUT_LOG, "w", encoding="utf-8"),
    stderr=open(ERR_LOG, "w", encoding="utf-8"),
)

print(f"Bot started PID: {proc.pid}")
print("Waiting 10s to verify...")
import time
time.sleep(10)

if proc.poll() is not None:
    print(f"Bot CRASHED with code {proc.returncode}")
    print("STDERR:", ERR_LOG.read_text()[:500])
else:
    print(f"Bot RUNNING (PID {proc.pid})")
    print("STDOUT:", OUT_LOG.read_text()[:500])
