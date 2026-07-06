#!/usr/bin/env python3
"""
GRAXIA-OS Live Trading Dashboard Server
Serves real-time bot state via HTTP on port 8080.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

BASE = Path(__file__).resolve().parent.parent
LOG_FILE = BASE / "logs" / "paper_trading.jsonl"
SESSION_FILE = BASE / "data" / "paper_trade_session.json"

MONITORING_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = MONITORING_DIR / "templates"
INDEX_HTML = TEMPLATES_DIR / "index.html"

app = FastAPI(title="GRAXIA-OS Dashboard")


def read_log_tail(n_lines: int = 50) -> list[str]:
    if not LOG_FILE.exists():
        return []
    data = LOG_FILE.read_bytes()
    raw = data.decode("utf-8", errors="replace")
    return raw.splitlines()[-n_lines:]


def load_session() -> dict:
    if not SESSION_FILE.exists():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def parse_status(lines: list[str]) -> dict:
    result = {
        "bid": 0.0,
        "ask": 0.0,
        "spread": 0.0,
        "confidence": 0.0,
        "prediction": "N/A",
        "position": None,
        "daily_pnl": 0.0,
        "daily_trades": 0,
        "balance": 49940.92,
        "uptime_seconds": 0,
        "session": "EU",
        "signal_strength": "weak",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "XGBoost (34 features)",
        "config": "stop=$3.00, conf>=0.75, EU only",
        "last_trade": None,
    }

    # Parse JSONL lines
    jsonl_entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            jsonl_entries.append(entry)
        except (json.JSONDecodeError, ValueError):
            continue

    if not jsonl_entries:
        return result

    # Extract fields from the most recent JSONL entries
    for entry in reversed(jsonl_entries):
        event = entry.get("event", "")

        if event == "trade_closed" or event == "trade_opened":
            result["last_trade"] = entry
            sym = entry.get("symbol", "")
            if sym:
                result["prediction"] = entry.get("side", result["prediction"])

        if "balance" in entry:
            result["balance"] = float(entry["balance"])

        if "drawdown_pct" in entry:
            result["daily_pnl"] = float(entry.get("daily_pnl", 0.0))

        if "confidence" in entry:
            c = float(entry["confidence"])
            result["confidence"] = c
            if c >= 0.75:
                result["signal_strength"] = "strong"
            elif c >= 0.60:
                result["signal_strength"] = "medium"
            else:
                result["signal_strength"] = "weak"

    # Derive timestamp from latest entry
    last_entry = jsonl_entries[-1]
    ts = last_entry.get("timestamp") or last_entry.get("time")
    if ts:
        result["timestamp"] = ts

    # Count trades
    result["daily_trades"] = sum(1 for e in jsonl_entries if e.get("event") in ("trade_opened", "trade_closed"))

    return result


def format_uptime(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


@app.get("/")
async def index():
    if INDEX_HTML.exists():
        content = INDEX_HTML.read_bytes().decode("utf-8")
        return HTMLResponse(content)
    return HTMLResponse("<h1>Dashboard template not found</h1>", status_code=404)


@app.get("/api/status")
async def api_status():
    lines = read_log_tail(60)
    status = parse_status(lines)
    return JSONResponse(status)


def main():
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    print(f"GRAXIA-OS Dashboard: http://localhost:{port}")
    print(f"Log file: {LOG_FILE}")
    print(f"HTML: {INDEX_HTML}")
    print()
    print("Start commands:")
    print('  $env:PYTHONIOENCODING="utf-8"')
    print("  python -m monitoring.dashboard_server")
    print(f"  # Open http://localhost:{port} in browser")
    print()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
