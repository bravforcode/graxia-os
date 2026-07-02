"""Process supervisor for shadow runner. Auto-restarts on crash."""
import subprocess
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("shadow_service")

MAX_RESTARTS = 50
RESTART_DELAY = 10  # seconds

def run():
    restarts = 0
    while restarts < MAX_RESTARTS:
        try:
            log.info(f"Starting shadow runner (attempt {restarts + 1})")
            result = subprocess.run(
                [sys.executable, "run_shadow.py"],
                cwd=str(Path(__file__).parent.parent),
                timeout=86400,  # 24h max
            )
            if result.returncode == 0:
                log.info("Shadow runner exited cleanly")
                break
            log.warning(f"Shadow runner exited with code {result.returncode}")
        except subprocess.TimeoutExpired:
            log.info("Shadow runner timeout — restarting for fresh state")
        except KeyboardInterrupt:
            log.info("Interrupted — shutting down")
            break
        except Exception as e:
            log.error(f"Shadow runner error: {e}")

        restarts += 1
        log.info(f"Restarting in {RESTART_DELAY}s...")
        time.sleep(RESTART_DELAY)

    log.info(f"Shadow service stopped after {restarts} restarts")

if __name__ == "__main__":
    from pathlib import Path
    run()
