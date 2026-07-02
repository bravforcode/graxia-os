"""Launcher for dry-run simulation — writes to file directly."""
import os, asyncio

os.environ["PYTHONIOENCODING"] = "utf-8"

# Write to file directly to avoid redirect issues
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "dry_run_1hr.log")
ERR_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "dry_run_1hr_err.log")

from quant_os.scripts.dry_run_simulator import run_dry_run
asyncio.run(run_dry_run(duration_minutes=60, interval_seconds=60))
