# Researcher State — Forex EA Verification (Doji / WallStreet / Team POW)

Date: 2026-08-04 | Task: verify 3 forex EAs (web research only, no code changes)

## Status: COMPLETE

## Findings Summary

### Doji EA (doji-pl-forex.com)
- Verdict: EXISTS as product+site, but UNVERIFIABLE track record. No Wayback history (CDX empty), no MyFxBook account found, site stats show placeholders (0% win rate / +0% ROI). Only performance data = forexroasted.com affiliate review (221%/18mo, 20.1% DD, no martingale, Polish-only support, dedicated asset manager).
- NOTE: dojiplfrxroasted URL = forexroasted referral lander (ref=frsrt). Affiliate relationship confirmed.
- Strategy claims (own site): 28 pairs 24/7, dynamic SL, "neural architecture", auto lot sizing, MT4/MT5, 3 risk profiles.

### WallStreet Forex Robot (wallstreet-forex.com)
- Verdict: REAL, verifiable, 15+ years old (launch ~Mar 22, 2011 per ForexRobotNation review).
- Vendor MyFxBook user `forexwallstreet` active since 2011-04-03; accounts: wallstreet-20-evolution-real (2016, Alpari RU, +77.85%, 19.99% DD), wallstreet-30-real-money-account (2022), recovery-pro demos (2015), eurusd 10254966, crypto 11957180, etc.
- Independent user accounts: `1000bay` (FXDD 2011, Pepperstone 2012, ThinkForex 2012, TitanFX 2016 +5.21%/12.62% DD), `10trades` (2012, 2016).
- Independent reviews: ForexRobotNation 2011-03-18 (launch review, $479) + 2017-11-20 FXProSystems review (vendor = FXProSystems; Wallstreet Asia EA: M15 Asian pullback scalper, 8 pairs, no martingale/grid, +400%/5.17% DD demo 2015-17).
- Strategy (forexroasted live test + official): 24/5 tick scalper, M15, EURUSD/GBPUSD/USDJPY, 5-8 pip targets, 3-5 trades/day, Asian session, Broker Spy module, optional Recovery Mode (martingale) OFF by default, extreme spread sensitivity (ECN/RAW required), one-time payment.
- FPA: bot-blocked (Cloudflare), no archived thread found → "no evidence found". MQL5: not found.

### Team POW (team-pow.com)
- Verdict: REAL business since Dec 2020 (Wayback), but NOT primarily an EA — "Done For You" MANAGED program: application → Typeform → strategy call → checkout (base/vip, pif, dfy, 18-month). Claims 8%/mo historical, $600K funded in 48h, 30-person scarcity.
- 2021 history: Wix site = 'EDGE' signal service (Discord) + 'BANKER' EA (24/5 buy+sell simultaneous) + Markets.com affiliate link. Founder Darren (darren_pow IG).
- Affiliate-heavy: bankerea?affiliate_id=..., theforexgeek partnership, Telegram/Twitter/TradingView traffic tags.
- Only review = forexroasted (52%/12mo, 3.9%/mo, 61% WR, 24.7% max DD, 4/12 losing months, multi-pair). No MyFxBook account found. Trustpilot blocked (403). theforexgeek: no results.

## Method Notes
- DDG lite/html + Mojeek + Brave + searx.be: all bot-blocked. Bing: garbage results (dictionary/Teams/WSJ).
- Usable: direct site fetches, r.jina.ai render proxy, Wayback CDX + archived MyFxBook pages, ForexRobotNation site search, forexroasted.com pages.
- Caveat: forexroasted is the ONLY source for Doji/TeamPOW performance; all 3 vendors' visit links carry ?ref=frsrt affiliate tags.

## Files Referenced (tool outputs)
- tool_fc9159161001efrfr8NXy5HSii (wallstreet homepage w/ MyFxBook widgets)
- tool_fc9168155001z9Xy9OSmR4lP25 (1000bay TitanFX 2016 archived stats)
- tool_fc91c94b10017EDBtfe7b1hi4V (forexwallstreet evolution real 2016 stats)
- tool_fc9179696001tScM1no2RSZ9zj / fc9179813001H7LX9Z2OYCFhdL / fc917991a001f7f7GpNHrpS90d (forexroasted reviews)
- tool_fc9196fce001K35JqPNnIp5Dp2 (doji site render), tool_fc91973ca0018yxuQPMNT0gEWw (team-pow 2021 archive)

## Next Steps (if resumed)
- Optional: fetch forexroasted /robots/wallstreet-forex-robot-review full key-results block (lines 48-77) for exact test numbers.
