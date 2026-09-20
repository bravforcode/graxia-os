"""Idempotently seed the ten AI Factory products into Graxia's funnel.

This script is fail-closed. It requires one operator-supplied delivery file
per product and publishes nothing when any file is missing. That prevents a
catalog row from pretending that a deliverable exists.

Usage:
    python scripts/seed_graxia_catalog.py \
      --base-url https://<verified-api-host> \
      --asset-dir C:\\path\\to\\graxia-assets

Each asset file is named `<slug>.md` and contains the actual deliverable text.
Binary files should be uploaded through the configured storage provider first;
this script intentionally does not upload or invent them.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

PRODUCTS = [
    ("prompt-pack-th", "Thai AI Prompt Pack", "AI prompts for Thai office and creator workflows.", 299, "prompt_pack"),
    ("obsidian-student-kit", "Obsidian Student Starter Kit", "A starter vault and setup guide for student notes.", 199, "kit"),
    ("freelance-pricing-calculator", "Thai Freelance Pricing Calculator", "A calculator for cost, time, scope, and quote inputs.", 149, "template"),
    ("cold-email-template-pack", "Cold Email Template Pack", "Bilingual outreach templates with adaptation notes.", 399, "template"),
    ("ai-automation-workflow", "AI Automation Workflow Pack", "Workflow examples with explicit review points.", 499, "kit"),
    ("cv-international-template", "International CV Template", "An editable CV structure and data checklist.", 199, "template"),
    ("n8n-sme-workflow-pack", "N8N SME Workflow Pack", "Workflow examples and node notes for SME automation.", 799, "kit"),
    ("content-calendar-90d", "90-Day Content Calendar", "A planning calendar with adaptable content prompts.", 599, "template"),
    ("finance-tracker-thb", "THB Finance Tracker", "A THB income and expense tracking template.", 149, "template"),
    ("ai-agent-starter-github", "AI Agent Starter for GitHub", "A starter project structure and extension guide.", 999, "kit"),
]


def _auth(client: httpx.Client) -> dict[str, str] | None:
    email = os.getenv("ADMIN_DEFAULT_EMAIL", os.getenv("ADMIN_EMAIL", ""))
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
    if not email or not password:
        print("Missing ADMIN_DEFAULT_EMAIL/ADMIN_DEFAULT_PASSWORD", file=sys.stderr)
        return None
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        print(f"Login failed ({response.status_code}): {response.text[:300]}", file=sys.stderr)
        return None
    token = response.json().get("access_token")
    if not token:
        print("Login response did not contain access_token", file=sys.stderr)
        return None
    csrf = client.cookies.get("csrf_token", "")
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--asset-dir", required=True)
    args = parser.parse_args()
    asset_dir = Path(args.asset_dir).expanduser().resolve()
    missing = [slug for slug, *_ in PRODUCTS if not (asset_dir / f"{slug}.md").is_file()]
    if missing:
        print("BLOCKED: missing delivery files:", file=sys.stderr)
        for slug in missing:
            print(f"  {asset_dir / f'{slug}.md'}", file=sys.stderr)
        return 2

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60, follow_redirects=True) as client:
        headers = _auth(client)
        if headers is None:
            return 1
        response = client.get("/api/v1/funnel/products", headers=headers)
        if response.status_code != 200:
            print(f"Product lookup failed ({response.status_code})", file=sys.stderr)
            return 1
        existing = {item.get("slug"): item for item in response.json()}
        failures = 0
        for slug, name, description, price, product_type in PRODUCTS:
            payload = {
                "name": name,
                "slug": slug,
                "short_description": description,
                "description": description,
                "price_amount": f"{price}.00",
                "currency": "THB",
                "product_type": product_type,
            }
            product = existing.get(slug)
            if product:
                update = client.patch(f"/api/v1/funnel/products/{product['id']}", json=payload, headers=headers)
                if update.status_code != 200:
                    print(f"FAILED update {slug} ({update.status_code})", file=sys.stderr)
                    failures += 1
                    continue
            else:
                create = client.post("/api/v1/funnel/products", json=payload, headers=headers)
                if create.status_code not in (200, 201):
                    print(f"FAILED create {slug} ({create.status_code}): {create.text[:240]}", file=sys.stderr)
                    failures += 1
                    continue
                product = create.json()
            assets = client.get(f"/api/v1/funnel/products/{product['id']}/assets", headers=headers)
            if assets.status_code != 200:
                print(f"FAILED asset lookup {slug} ({assets.status_code})", file=sys.stderr)
                failures += 1
                continue
            if not any(item.get("is_active") for item in assets.json()):
                asset = client.post(
                    f"/api/v1/funnel/products/{product['id']}/assets",
                    json={
                        "asset_type": "content",
                        "title": f"{name} delivery asset",
                        "content_body": (asset_dir / f"{slug}.md").read_text(encoding="utf-8"),
                    },
                    headers=headers,
                )
                if asset.status_code not in (200, 201):
                    print(f"FAILED asset {slug} ({asset.status_code})", file=sys.stderr)
                    failures += 1
                    continue
            publish = client.post(f"/api/v1/funnel/products/{product['id']}/publish", headers=headers)
            if publish.status_code != 200:
                print(f"FAILED publish {slug} ({publish.status_code})", file=sys.stderr)
                failures += 1
                continue
            print(f"OK {slug} published with operator-supplied asset")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
