"""
notebooklm_refresh.py — Auto-refresh NotebookLM auth every 12 hours
Run: python scripts/notebooklm_refresh.py
Or schedule as daily task.
"""
import subprocess, sys, json, io
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LOG_DIR = Path(__file__).resolve().parent.parent / "Meta" / "states"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def run_cmd(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1

def check_auth():
    stdout, stderr, code = run_cmd(["notebooklm", "auth", "check"], timeout=15)
    combined = (stdout + stderr).lower()
    if "authentication is valid" in combined or ("pass" in combined and "cookies" in combined):
        return True
    if "expired" in combined or "invalid" in combined or "redirected" in combined:
        return False
    return None

def test_api():
    stdout, stderr, code = run_cmd(["notebooklm", "list"], timeout=20)
    combined = (stdout + stderr).lower()
    if "unexpected error" in combined or "redirected" in combined or "expired" in combined:
        return False
    if "notebook" in combined or "quant" in combined or "arween" in combined:
        return True
    return None

def refresh_auth():
    log("Re-logging in to NotebookLM...")
    stdout, stderr, code = run_cmd(["notebooklm", "login"], timeout=60)
    log(f"Login exit code: {code}")
    if stdout:
        log(f"Login output: {stdout[:300]}")
    return code == 0

def main():
    log("=== NotebookLM Auth Refresh ===")
    
    auth_ok = check_auth()
    log(f"Auth check: {'VALID' if auth_ok else 'EXPIRED' if auth_ok is False else 'UNKNOWN'}")
    
    api_ok = test_api()
    log(f"API test: {'WORKING' if api_ok else 'FAILED' if api_ok is False else 'UNKNOWN'}")
    
    refreshed = False
    if auth_ok is False or api_ok is False:
        log("Auth expired or API failed. Re-logging in...")
        if refresh_auth():
            refreshed = True
            auth_ok = check_auth()
            api_ok = test_api()
            log(f"After refresh: auth={'OK' if auth_ok else 'FAIL'}, api={'OK' if api_ok else 'FAIL'}")
        else:
            log("Re-login failed!")
    else:
        log("Auth is valid. No refresh needed.")
    
    state = {
        "timestamp": datetime.now().isoformat(),
        "auth_valid": auth_ok,
        "api_working": api_ok,
        "refreshed": refreshed
    }
    (LOG_DIR / "notebooklm_auth_state.json").write_text(json.dumps(state, indent=2))
    log(f"State saved. Auth={'OK' if auth_ok else 'EXPIRED'}, API={'OK' if api_ok else 'FAILED'}")
    return 0 if (auth_ok and api_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
