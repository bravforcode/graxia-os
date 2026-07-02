import json
import re
import sys
import time
import tomllib
from datetime import datetime, UTC
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "scripts" / "telegram_config.toml"
LOG_PATH = BASE / "artifacts" / "mega_data" / "mega_collect.log"
SUMMARY_PATH = BASE / "artifacts" / "mega_data" / "run_summary.json"
STATE_PATH = BASE / "artifacts" / "mega_data" / ".telegram_state.json"
POLL_INTERVAL = 60

with open(CONFIG_PATH, "rb") as f:
    cfg = tomllib.load(f)
BOT_TOKEN = cfg["bot_token"]
CHAT_ID = cfg["chat_id"]

if BOT_TOKEN == "YOUR_BOT_TOKEN":
    print("config: set bot_token and chat_id in scripts/telegram_config.toml", file=sys.stderr)
    sys.exit(1)


def send_msg(text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=15)
        return r.ok
    except requests.RequestException as e:
        print(f"send failed: {e}", file=sys.stderr)
        return False


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_size": 0, "last_balance": None, "last_seen_errors": 0}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def check_log(state: dict) -> list[str]:
    msgs = []
    if not LOG_PATH.exists():
        return ["no log file yet"]

    cur_size = LOG_PATH.stat().st_size
    if cur_size == state.get("last_size", 0):
        return []

    with open(LOG_PATH) as f:
        content = f.read()

    lines = content.splitlines()
    new_lines = []
    if state.get("last_size", 0) > 0:
        known_len = len(content[: state["last_size"]].splitlines())
        new_lines = lines[known_len:]
    else:
        new_lines = lines

    rejected = [l for l in new_lines if "REJECTED" in l.upper()]
    if rejected:
        msgs.append(f"<b>REJECTED orders</b> ({len(rejected)}):\n" + "\n".join(l.strip() for l in rejected[-5:]))

    error_lines = [l for l in new_lines if re.search(r"error|exception|traceback", l, re.I)]
    if error_lines:
        prev_errs = state.get("last_seen_errors", 0)
        cur_errs = len(error_lines)
        new_err_count = cur_errs - prev_errs
        if new_err_count > 0:
            msgs.append(f"<b>Errors</b> ({new_err_count} new):\n" + "\n".join(l.strip() for l in error_lines[-3:]))
        state["last_seen_errors"] = cur_errs

    state["last_size"] = cur_size
    return msgs


def check_balance(state: dict) -> list[str]:
    msgs = []
    if not SUMMARY_PATH.exists():
        return msgs

    try:
        with open(SUMMARY_PATH) as f:
            summary = json.load(f)
    except (json.JSONDecodeError, OSError):
        return msgs

    cur_balance = summary.get("balance")
    prev = state.get("last_balance")
    if cur_balance is not None and prev is not None:
        diff = cur_balance - prev
        if abs(diff) > 1:
            emoji = "\U0001f4c8" if diff > 0 else "\U0001f4c9"
            ts = summary.get("completed_at_utc", datetime.now(UTC).isoformat())
            msgs.append(f"{emoji} <b>Balance change</b>: ${prev:,.2f} \u2192 ${cur_balance:,.2f} ({diff:+.2f}) @ {ts}")

    if cur_balance is not None:
        state["last_balance"] = cur_balance
    return msgs


def main():
    state = load_state()
    send_msg(f"\U0001f916 <b>Telegram Monitor started</b>\nPolling {LOG_PATH} every {POLL_INTERVAL}s")
    save_state(state)

    while True:
        time.sleep(POLL_INTERVAL)
        msgs = check_log(state) + check_balance(state)
        for m in msgs:
            send_msg(m)
        save_state(state)


if __name__ == "__main__":
    main()
