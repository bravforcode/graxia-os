# Researcher State — EATested Best Forex EA 2026 Extraction

**Date:** 2026-08-04
**Task:** Extract complete ranking table from https://eatested.com/best-forex-eas/

## Status: COMPLETE

## Key Findings
- **51 EAs** extracted from main ranking table (verified against raw HTML: 51 `go/` links, 51 "Learn More" links, 52 `<tr>` = 51 rows + 1 header).
- All rows: Live Test = **Real**.
- Table sorted by Monthly (Real Gain) descending (Zone Hunter Robot 33.4% → Omega Trend EA 1.0%).
- Fetch note: markdown fetch truncated → full output saved by tool; re-fetched as HTML to verify row count. Direct Invoke-WebRequest gets 403 (bot protection); webfetch works.

## ⚠️ Discrepancy (IMPORTANT for requester)
- The brief mentioned a **"Top Rated" shortlist** (FXStabilizer Pro, WallStreet Robot, Forex Gold Investor) and a **"Veteran EAs: 1000+ Days Live"** section (FXStabilizer Pro 3766 days, Happy Gold 1874 days, Money Tree 1636 days).
- **These sections DO NOT exist on the current page.** Verified via raw HTML grep: zero matches for `veteran`, `3766`, `1874`, `1636`, `1000+ days`.
- The main table IS titled "Top Rated Forex Robots & EAs (Tested 2026)". FXStabilizer EA, WallStreet Forex Robot 3.0, Forex Gold Investor appear as regular rows (#39, #44, #15).
- Do NOT guess day-counts; they may live on individual review pages (not fetched).

## Files
- Markdown fetch: `tool_fc93d731b0017SyPyTkq4xABll` (1361 lines)
- HTML fetch: `tool_fc93e6689001CwZoyO7WxbUZwA` (~368KB)

## Next Steps (if requester insists on day counts)
- Fetch each of the 3 review pages: /fxstabilizer-ea-review, /wallstreet-forex-robot, /happy-gold-ea-review, /the-money-tree-ea and look for "days" on MyFXBook stats.
