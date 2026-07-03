"""Launcher for 24-hour dry-run simulation."""
import os, asyncio

os.environ["PYTHONIOENCODING"] = "utf-8"

from quant_os.scripts.dry_run_simulator import run_dry_run
asyncio.run(run_dry_run(duration_minutes=1440, interval_seconds=60))
