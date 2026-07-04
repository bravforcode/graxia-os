"""
Windows Task Scheduler setup for daily state backup.

Creates a scheduled task that runs backup_state.py daily at 02:00 UTC.

Usage (run as Administrator):
    python scripts/setup_backup_task.py           # create task
    python scripts/setup_backup_task.py --remove  # remove task
    python scripts/setup_backup_task.py --status  # check task status
"""

import subprocess
import sys
from pathlib import Path

TASK_NAME = "QuantOS_DailyStateBackup"
SCRIPT_PATH = Path(__file__).resolve().parent / "backup_state.py"
PYTHON_PATH = sys.executable
TRIGGER_TIME = "02:00"  # Daily at 02:00 UTC


def create_task():
    """Create the scheduled task via schtasks."""
    cmd = [
        "schtasks",
        "/create",
        "/tn",
        TASK_NAME,
        "/tr",
        f'"{PYTHON_PATH}" "{SCRIPT_PATH}"',
        "/sc",
        "daily",
        "/st",
        TRIGGER_TIME,
        "/f",  # force overwrite if exists
    ]
    print(f"Creating task: {TASK_NAME}")
    print(f"  Script: {SCRIPT_PATH}")
    print(f"  Python: {PYTHON_PATH}")
    print(f"  Schedule: Daily at {TRIGGER_TIME} UTC")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Task created successfully.")
        print(result.stdout)
    else:
        print(f"Error creating task (exit {result.returncode}):")
        print(result.stderr)
        sys.exit(1)


def remove_task():
    """Remove the scheduled task."""
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Task '{TASK_NAME}' removed.")
    else:
        print(f"Error: {result.stderr}")
        sys.exit(1)


def show_status():
    """Show task status."""
    cmd = ["schtasks", "/query", "/tn", TASK_NAME, "/v", "/fo", "list"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"Task not found or error: {result.stderr}")


def main():
    args = sys.argv[1:]

    if "--remove" in args:
        remove_task()
    elif "--status" in args:
        show_status()
    else:
        create_task()


if __name__ == "__main__":
    main()
