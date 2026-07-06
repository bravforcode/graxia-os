"""
Gold Bot Health Check — runs every hour via Scheduled Task.

Checks:
1. Is the bot process alive?
2. Is MT5 terminal running?
3. Is the log file growing? (not stuck)
4. Any errors in the error log?
5. Auto-restart if bot is dead.

Usage:
    python gold_bot/health_check.py
    python gold_bot/health_check.py --auto-restart
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Paths
WORKSPACE = Path(r"C:\Users\menum\graxia os")
LOG_DIR = WORKSPACE / "graxia" / "packages" / "quant_os" / "logs"
HEALTH_LOG = LOG_DIR / "health_check.log"
PID_FILE = LOG_DIR / "paper_7day.pid"
BOT_LOG = LOG_DIR / "paper_7day.log"
ERR_LOG = LOG_DIR / "paper_7day_err.log"
LAUNCHER = WORKSPACE / "graxia" / "packages" / "quant_os" / "launch_7day.py"
BOT_SCRIPT = WORKSPACE / "graxia" / "packages" / "quant_os" / "gold_bot" / "run_paper.py"


def log(msg: str):
    """Write to health check log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(HEALTH_LOG, "a") as f:
        f.write(line + "\n")


def check_process_alive(pid: int) -> bool:
    """Check if a process is running by PID."""
    try:
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=10)
        return str(pid) in result.stdout
    except Exception:
        return False


def check_bot_process() -> tuple[bool, int]:
    """Check if bot process is alive. Returns (alive, pid)."""
    # Check PID file first
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if check_process_alive(pid):
                return True, pid
        except (ValueError, OSError):
            pass

    # Fallback: find python or cmd process running run_paper.py via PowerShell
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='cmd.exe'\" "
                "| Where-Object { $_.CommandLine -like '*run_paper.py*' } "
                "| Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                if pid > 0:
                    PID_FILE.write_text(str(pid))
                    return True, pid
    except Exception:
        pass

    return False, 0


def check_mt5_running() -> bool:
    """Check if MT5 terminal is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"], capture_output=True, text=True, timeout=10
        )
        return "terminal64.exe" in result.stdout
    except Exception:
        return False


def check_log_growing() -> bool:
    """Check if bot log file is still being written to (growing)."""
    if not BOT_LOG.exists():
        return False

    size1 = BOT_LOG.stat().st_size
    import time

    time.sleep(3)
    size2 = BOT_LOG.stat().st_size

    return size2 > size1  # Growing = bot is active


def check_error_log() -> list[str]:
    """Read recent errors from error log."""
    errors = []
    if ERR_LOG.exists():
        content = ERR_LOG.read_text(encoding="utf-8").strip()
        if content:
            # Get last 5 lines
            lines = content.split("\n")
            errors = lines[-5:]
    return errors


def check_csv_activity() -> dict:
    """Check trade CSV activity."""
    import glob

    # Check both possible locations for CSV
    csv_files = sorted(glob.glob(str(LOG_DIR / "paper_trades_*.csv")))
    if not csv_files:
        alt_dir = WORKSPACE / "logs"
        csv_files = sorted(glob.glob(str(alt_dir / "paper_trades_*.csv")))
    if not csv_files:
        return {"exists": False, "trades": 0, "latest_file": None}

    latest = csv_files[-1]
    try:
        with open(latest) as f:
            lines = f.readlines()
            trade_count = max(0, len(lines) - 1)  # Subtract header
    except Exception:
        trade_count = 0

    mtime = datetime.fromtimestamp(Path(latest).stat().st_mtime).strftime("%H:%M:%S")
    return {
        "exists": True,
        "trades": trade_count,
        "latest_file": Path(latest).name,
        "last_modified": mtime,
    }


def restart_bot():
    """Restart the paper trading bot via PowerShell script."""
    log("RESTARTING bot...")

    # Kill existing processes
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process python,cmd -ErrorAction SilentlyContinue | "
                "Where-Object { $_.CommandLine -like '*run_paper*' } | Stop-Process -Force",
            ],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        pass

    import time

    time.sleep(5)

    # Start via PS1 script
    ps1_script = WORKSPACE / "graxia" / "packages" / "quant_os" / "start_bot.ps1"
    try:
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1_script)],
            cwd=str(WORKSPACE),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        log("Bot restart initiated via start_bot.ps1")
        return True
    except Exception as e:
        log(f"RESTART FAILED: {e}")
        return False


def run_health_check(auto_restart: bool = False) -> dict:
    """Run full health check."""
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "bot_alive": False,
        "bot_pid": 0,
        "mt5_running": False,
        "log_growing": False,
        "errors": [],
        "csv": {},
        "action": "none",
    }

    log("=" * 60)
    log("HEALTH CHECK START")

    # 1. Check bot process
    alive, pid = check_bot_process()
    report["bot_alive"] = alive
    report["bot_pid"] = pid
    log(f"Bot process: {f'ALIVE (PID={pid})' if alive else 'DEAD'}")

    # 2. Check MT5
    mt5 = check_mt5_running()
    report["mt5_running"] = mt5
    log(f"MT5 terminal: {'RUNNING' if mt5 else 'NOT RUNNING'}")

    # 3. Check log growing (only if bot alive)
    if alive:
        growing = check_log_growing()
        report["log_growing"] = growing
        log(f"Log growing: {'YES' if growing else 'NO (STUCK?)'}")

    # 4. Check errors
    errors = check_error_log()
    report["errors"] = errors
    if errors:
        log(f"Errors found: {len(errors)}")
        for e in errors:
            log(f"  ERR: {e}")
    else:
        log("No errors in error log")

    # 5. Check CSV
    csv_info = check_csv_activity()
    report["csv"] = csv_info
    log(f"Trades: {csv_info['trades']} (file: {csv_info.get('latest_file', 'none')})")

    # 6. Auto-restart if needed
    if not alive and auto_restart:
        report["action"] = "restart"
        restart_bot()
    elif not mt5 and alive:
        report["action"] = "mt5_dead"
        log("WARNING: MT5 is dead but bot is alive. Manual intervention needed.")
    elif alive and not report.get("log_growing", True):
        report["action"] = "log_stuck"
        log("WARNING: Bot alive but log not growing. May be stuck.")

    log(f"ACTION: {report['action']}")
    log("HEALTH CHECK END")
    log("=" * 60)

    return report


if __name__ == "__main__":
    auto = "--auto-restart" in sys.argv
    report = run_health_check(auto_restart=auto)

    # Save report as JSON
    report_file = LOG_DIR / "health_report_latest.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Exit code: 0=healthy, 1=degraded, 2=critical
    if report["bot_alive"] and report["mt5_running"]:
        sys.exit(0)
    elif report["bot_alive"] or report["mt5_running"]:
        sys.exit(1)
    else:
        sys.exit(2)
