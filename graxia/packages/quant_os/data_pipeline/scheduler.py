"""
scheduler.py — Automated Data Pipeline Schedules
Registers Windows scheduled tasks for data pipeline
"""
import subprocess
import sys
from pathlib import Path


def create_scheduled_task(name: str, script: str, schedule: str, description: str):
    """Create a Windows scheduled task (shell=False for security)."""
    py = sys.executable
    cmd = [
        "schtasks", "/create",
        "/tn", name,
        "/tr", f"{py} {script}",
        "/sc", schedule,
        "/f", "/rl", "HIGHEST",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  OK: {name}")
    else:
        print(f"  FAIL: {name}: {result.stderr[:100]}")


def register_all_schedules():
    """Register all pipeline schedules"""
    base = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline")
    py = sys.executable

    print("=== Registering Data Pipeline Schedules ===")

    # 1. Full pipeline — daily at 5 AM
    create_scheduled_task(
        "QuantOS-DataPipeline-Full",
        str(base / "pipeline.py"),
        "daily /st 05:00",
        "Full data pipeline — all sources"
    )

    # 2. Market data — every 15 min during market hours
    create_scheduled_task(
        "QuantOS-MarketData",
        str(base / "orchestration" / "flows.py"),
        "daily /st 06:00 /du 12:00 /sc minute /mo 15",
        "Market data refresh — every 15 min"
    )

    # 3. News sentiment — every 4 hours
    create_scheduled_task(
        "QuantOS-NewsSentiment",
        str(base / "orchestration" / "flows.py"),
        "daily /st 06:00 /sc hourly /mo 4",
        "News + sentiment analysis — every 4 hours"
    )

    # 4. Vault sync — daily at 6 AM
    create_scheduled_task(
        "QuantOS-VaultSync",
        str(base / "pipeline.py"),
        "daily /st 06:00",
        "Sync vault strategies to ChromaDB"
    )

    print("\nAll schedules registered!")


if __name__ == "__main__":
    register_all_schedules()
