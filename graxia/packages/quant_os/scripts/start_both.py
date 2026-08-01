"""Start spread measurement + paper trade bot as background processes."""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = BASE.parent.parent  # graxia/os/

SPREAD_SCRIPT = BASE / "scripts" / "measure_spread.py"
PAPER_SCRIPT = BASE / "scripts" / "paper_trade_bot.py"
LOGS_DIR = BASE / "logs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)

def start_process(name, script, args=None, cwd=None):
    """Start a background process with log redirection."""
    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend(args)

    log_out = LOGS_DIR / f"{name}_stdout.log"
    log_err = LOGS_DIR / f"{name}_stderr.log"

    with open(log_out, "w") as f_out, open(log_err, "w") as f_err:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd or GRAXIA_ROOT),
            stdout=f_out,
            stderr=f_err,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    print(f"  {name}: PID={proc.pid} | stdout={log_out} | stderr={log_err}")
    return proc

def main():
    print("Starting spread measurement + paper trade bot...")
    print(f"  Base: {BASE}")
    print(f"  Graxia root: {GRAXIA_ROOT}")
    print()

    # Start spread measurement
    spread = start_process(
        "spread",
        SPREAD_SCRIPT,
        args=["--interval", "60", "--symbols", "XAUUSD,EURUSD,GBPUSD,BTCUSD"],
        cwd=GRAXIA_ROOT,
    )

    # Wait a bit for MT5 to initialize
    time.sleep(5)

    # Start paper trade bot
    paper = start_process(
        "paper",
        PAPER_SCRIPT,
        args=["--symbol", "XAUUSD"],
        cwd=GRAXIA_ROOT,
    )

    print()
    print(f"Both processes started:")
    print(f"  Spread measurement: PID={spread.pid}")
    print(f"  Paper trade bot: PID={paper.pid}")
    print()
    print("Check logs:")
    print(f"  logs/spread_stdout.log")
    print(f"  logs/spread_stderr.log")
    print(f"  logs/paper_stdout.log")
    print(f"  logs/paper_stderr.log")
    print()
    print("To stop: taskkill /PID {spread.pid} /PID {paper.pid}")

if __name__ == "__main__":
    main()
