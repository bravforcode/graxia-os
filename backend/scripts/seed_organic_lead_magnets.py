"""Create the three organic lead magnets idempotently.

The script is intentionally fail-closed: it will not publish a lead magnet
unless its target product already exists in the selected organization.

Usage:
    python scripts/seed_organic_lead_magnets.py --base-url https://api.example

Credentials come from ADMIN_DEFAULT_EMAIL / ADMIN_DEFAULT_PASSWORD (or the
ADMIN_EMAIL / ADMIN_PASSWORD aliases). Provider secrets are never accepted as
arguments and are not written to files.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

LEAD_MAGNETS = [
    {
        "name": "Prompt Pack Lite",
        "slug": "prompt-pack-lite",
        "promise": "A starter prompt set for recurring work.",
        "target_product_slugs": ("prompt-pack-th", "ai-prompt-pack-50"),
        "landing_page_url": "https://graxia.store/free/prompt-pack-lite",
    },
    {
        "name": "Freelance Pricing Calculator Lite",
        "slug": "freelance-pricing-calculator-lite",
        "promise": "A checklist for pricing work from cost and time.",
        "target_product_slugs": ("freelance-pricing-calculator",),
        "landing_page_url": "https://graxia.store/free/freelance-pricing-calculator-lite",
    },
    {
        "name": "N8N/SME Automation Checklist",
        "slug": "n8n-sme-automation-checklist",
        "promise": "A checklist for finding the first workflows to automate.",
        "target_product_slugs": ("n8n-sme-workflow-pack",),
        "landing_page_url": "https://graxia.store/free/n8n-sme-automation-checklist",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    email = os.getenv("ADMIN_DEFAULT_EMAIL", os.getenv("ADMIN_EMAIL", ""))
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
    if not email or not password:
        print("Missing ADMIN_DEFAULT_EMAIL/ADMIN_DEFAULT_PASSWORD", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=60, follow_redirects=True) as client:
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            print(f"Login failed ({login.status_code}): {login.text[:300]}", file=sys.stderr)
            return 1
        token = login.json().get("access_token")
        if not token:
            print("Login response did not contain access_token", file=sys.stderr)
            return 1
        csrf = client.cookies.get("csrf_token", "")
        headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}

        products_response = client.get("/api/v1/funnel/products", headers=headers)
        if products_response.status_code != 200:
            print(f"Product lookup failed ({products_response.status_code})", file=sys.stderr)
            return 1
        products = products_response.json()
        by_slug = {item.get("slug"): item for item in products}

        magnets_response = client.get("/api/v1/funnel/lead-magnets", headers=headers)
        if magnets_response.status_code != 200:
            print(f"Lead magnet lookup failed ({magnets_response.status_code})", file=sys.stderr)
            return 1
        existing = {item.get("slug"): item for item in magnets_response.json()}

        failures = 0
        for definition in LEAD_MAGNETS:
            target = next((by_slug.get(slug) for slug in definition["target_product_slugs"] if by_slug.get(slug)), None)
            if not target:
                print(f"BLOCKED {definition['slug']}: target product is missing", file=sys.stderr)
                failures += 1
                continue
            payload = {
                "name": definition["name"],
                "slug": definition["slug"],
                "promise": definition["promise"],
                "target_product_id": target["id"],
                "landing_page_url": definition["landing_page_url"],
            }
            current = existing.get(definition["slug"])
            if current:
                response = client.put(f"/api/v1/funnel/lead-magnets/{current['id']}", json={**payload, "status": "published"}, headers=headers)
            else:
                response = client.post("/api/v1/funnel/lead-magnets", json=payload, headers=headers)
                if response.status_code in (200, 201):
                    current = response.json()
            if response.status_code not in (200, 201):
                print(f"FAILED {definition['slug']} ({response.status_code}): {response.text[:240]}", file=sys.stderr)
                failures += 1
                continue
            magnet_id = (current or response.json()).get("id")
            publish = client.put(f"/api/v1/funnel/lead-magnets/{magnet_id}", json={"status": "published"}, headers=headers)
            if publish.status_code != 200:
                print(f"FAILED publish {definition['slug']} ({publish.status_code})", file=sys.stderr)
                failures += 1
            else:
                print(f"OK {definition['slug']} -> {target['slug']}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
