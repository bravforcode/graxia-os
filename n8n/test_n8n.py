"""Auto-test n8n: setup owner, import workflows, configure Resend, execute.

Secrets come from the environment (or .env.production via python-dotenv).
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.production"))

BASE = "http://localhost:5678"
ADMIN_EMAIL = os.environ.get("ADMIN_DEFAULT_EMAIL", "admin@graxia.store")
ADMIN_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "")
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
WORKFLOWS_DIR = Path(__file__).parent / "workflows"


def main() -> int:
    # 1. Wait for n8n
    for i in range(60):
        try:
            r = httpx.get(f"{BASE}/healthz", timeout=5)
            if r.status_code == 200:
                print(f"n8n UP after {i * 10}s")
                break
        except Exception:
            pass
        time.sleep(10)
    else:
        print("n8n did not start")
        return 1

    c = httpx.Client(base_url=BASE, timeout=60, follow_redirects=True)

    # 2. Owner setup (409 = already set up)
    r = c.post("/rest/owner/setup", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "firstName": "Admin", "lastName": "User"})
    print(f"owner setup: {r.status_code} {r.text[:120]}")

    # 3. Login
    r = c.post("/rest/login", json={"emailOrLdapLoginId": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    print(f"login: {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return 1

    # 4. Resend credential
    r = c.post(
        "/rest/credentials",
        json={"name": "Resend API", "type": "resendApi", "data": {"apiKey": RESEND_KEY}},
    )
    print(f"credential resend: {r.status_code}")
    cred_id = r.json().get("data", {}).get("id") if r.status_code in (200, 201) else None
    print(f"credential id: {cred_id}")

    # 5. Import workflows (patch from-address to onboarding@resend.dev)
    for wf_file in sorted(WORKFLOWS_DIR.glob("*.json")):
        if wf_file.name.startswith(("daily_scan", "weekly_review", "content_engine")):
            continue  # legacy workflows reference old infra
        data = json.loads(wf_file.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            if node.get("type") == "n8n-nodes-base.resend":
                node["parameters"]["from"] = "Ai Factory <onboarding@resend.dev>"
                if cred_id:
                    node["credentials"] = {"resendApi": {"id": cred_id, "name": "Resend API"}}
        r = c.post("/rest/workflows", json={"name": data["name"], "nodes": data["nodes"], "connections": data["connections"], "settings": data.get("settings", {})})
        wf_id = r.json().get("data", {}).get("id") if r.status_code in (200, 201) else None
        print(f"import {wf_file.name}: {r.status_code} id={wf_id}")

    # 6. Execute store-monitor (test run)
    r = c.post(f"{BASE}/rest/workflows/0/run", json={})  # placeholder
    # find the imported store-monitor id from list
    r = c.get("/rest/workflows")
    wfs = r.json().get("data", [])
    for wf in wfs:
        if "Monitor" in wf.get("name", ""):
            wf_id = wf["id"]
            print(f"executing store-monitor (id={wf_id})...")
            try:
                ex = c.post(f"/rest/workflows/{wf_id}/run", json={"startNodes": ["Check /health"]})
                print(f"run: {ex.status_code} {ex.text[:200]}")
            except Exception as exc:
                print(f"run failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
