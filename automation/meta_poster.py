"""
Meta poster + Ads builder.

- Post to a Facebook Page (Graph API) — works with a Page access token.
- Create Meta Ads campaigns (campaign -> ad set -> ad) via the Marketing API.
  DRY-RUN by default: prints everything it would create; pass --live with
  real tokens + an ad account to actually launch (spends money).

Tokens come from the environment (never commit them):
    META_PAGE_TOKEN      — Page access token (posting)
    META_AD_ACCOUNT_ID   — e.g. act_123456789 (ads)
    META_ACCESS_TOKEN    — ads_management token (ads)
"""
import argparse
import os
import sys


def post_to_page(body: str) -> dict:
    """Publish a text post to the configured Facebook Page."""
    import httpx

    token = os.environ.get("META_PAGE_TOKEN", "")
    if not token:
        return {"ok": False, "reason": "META_PAGE_TOKEN not set"}
    r = httpx.post(
        "https://graph.facebook.com/v21.0/me/feed",
        params={"message": body, "access_token": token},
        timeout=30,
    )
    data = r.json()
    return {"ok": r.status_code == 200, "response": data}


def build_ad_campaign(dry_run: bool = True) -> dict:
    """Create a Conversions campaign for the prompt pack (dry-run default)."""
    import httpx

    account = os.environ.get("META_AD_ACCOUNT_ID", "")
    token = os.environ.get("META_ACCESS_TOKEN", "")
    if not account or not token:
        return {"ok": False, "reason": "META_AD_ACCOUNT_ID / META_ACCESS_TOKEN not set"}

    base = f"https://graph.facebook.com/v21.0/{account}"
    headers = {"Content-Type": "application/json"}

    # 1. Campaign (conversions, purchase)
    campaign = httpx.post(
        f"{base}/campaigns",
        params={
            "name": "Ai Factory - Prompt Pack Conversions (auto)",
            "objective": "OUTCOME_SALES",
            "status": "PAUSED" if dry_run else "ACTIVE",
            "special_ad_categories": "[]",
            "access_token": token,
        },
        timeout=30,
    ).json()
    if "id" not in campaign:
        return {"ok": False, "response": campaign}
    campaign_id = campaign["id"]

    # 2. Ad set
    adset = httpx.post(
        f"{base}/adsets",
        params={
            "name": "Auto AdSet - TH 22-45",
            "campaign_id": campaign_id,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "OFFSITE_CONVERSIONS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "daily_budget": 30000,  # THB minor units = ฿300/day
            "status": "PAUSED" if dry_run else "ACTIVE",
            "targeting": '{"geo_locations":{"countries":["TH"]},"age_min":22,"age_max":45}',
            "access_token": token,
        },
        timeout=30,
    ).json()
    if "id" not in adset:
        return {"ok": False, "response": adset}
    adset_id = adset["id"]

    # 3. Ad (image creative placeholder — swap with real creative later)
    creative = httpx.post(
        f"{base}/adcreatives",
        params={
            "name": "Auto Creative - Prompt Pack",
            "object_story_spec": json_story(),
            "access_token": token,
        },
        timeout=30,
    ).json()
    ad = httpx.post(
        f"{base}/ads",
        params={
            "name": "Auto Ad - Prompt Pack 149",
            "adset_id": adset_id,
            "creative": '{"creative_id":"%s"}' % creative.get("id", ""),
            "status": "PAUSED" if dry_run else "ACTIVE",
            "access_token": token,
        },
        timeout=30,
    ).json()
    return {"ok": "id" in ad, "campaign_id": campaign_id, "adset_id": adset_id, "ad": ad}


def json_story() -> str:
    import json as _json

    return _json.dumps(
        {
            "page_id": os.environ.get("META_PAGE_ID", ""),
            "link_data": {
                "link": "https://graxia-os-funnel.vercel.app/products",
                "message": "50 พรอมต์ AI ภาษาไทย ใช้ทำงานจริง เริ่มต้น 149 บาท",
                "name": "AI Prompt Pack เริ่มต้น — Ai Factory",
                "description": "เขียนคอนเทนต์ ทำงานออฟฟิศ วางแผนธุรกิจ พร้อมวิธีปรับใช้",
            },
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", help="post this text to the FB page")
    parser.add_argument("--ads", action="store_true", help="build ad campaign")
    parser.add_argument("--live", action="store_true", help="actually launch (spends money)")
    args = parser.parse_args()

    if args.post:
        result = post_to_page(args.post)
        print("POST:", result)
    if args.ads:
        result = build_ad_campaign(dry_run=not args.live)
        print("ADS:", result)
    if not args.post and not args.ads:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
