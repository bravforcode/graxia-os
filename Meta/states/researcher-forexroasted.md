# Researcher state — ForexRoasted audit + EA mechanics (2026-08-04)

Status: COMPLETE (web research only; no code touched)

## Deliverables produced
- PART 1 verdict: affiliate disclosure NOT found; methodology unverifiable (no account IDs); credibility LOW.
- PART 2: documented EA mechanics with URLs (Wikipedia martingale, Investopedia grid/scalping via wayback, wallstreet-forex.com official, forexroasted.com/robots own grid/martingale blowup case).

## Key evidence (with URLs)
- https://forexroasted.com/methodology — "Zero Affiliate Bias", "ratings are never influenced by affiliate commissions". No disclosure.
- https://forexroasted.com/robots — every "Visit X" link has ?ref=frsrt: ea-auto-matic.online/sat?ref=frsrt (#1), bullcharge-automation.ink/bc-mainpage?ref=frsrt (#2), doji-pl-forex.com/dojiplfrxroasted?ref=frsrt (#3), wallstreet-forex.com/?ref=frsrt (#4), team-pow.com/?ref=frsrt (#5), forexfury.com/?ref=frsrt (#6). #7 Dot Trading: "Grid/martingale strategy blew account during minor volatility spike... Classic scam pattern". Claim: "Trades verified against broker statements" — no account IDs/links anywhere on page.
- https://forexroasted.com/truth — exists; footer disclaimer: "Trading CFDs and Forex involves substantial risk... informational purposes only".
- https://forexroasted.com/risk-disclosure — standard CFD risk warning; no affiliate disclosure.
- Whois forexroasted.com: NameCheap, registered 2025-10-12, "Withheld for Privacy ehf" (Iceland), client transfer prohibited.
- Whois ea-auto-matic.online: NameCheap, registered 2026-06-10 (contradicts claimed 18-month test starting Jan 2024), same privacy/registrar pattern, client transfer prohibited.
- https://en.wikipedia.org/wiki/Martingale_(betting_system) — doubling after loss; 6-loss streak ≥84% likely within 200 plays; 10 losses = 1,023× original bet; negative EV proof.
- https://web.archive.org/web/2024id_/https://www.investopedia.com/terms/g/grid-trading.asp — grid = orders at intervals; against-trend grid risk uncontrolled in trending market; requires stop.
- https://web.archive.org/web/2024id_/https://www.investopedia.com/terms/s/scalping.asp — 10–hundreds of trades/day, small TP, leverage = high risk, heavy commissions.
- https://www.wallstreet-forex.com/ — official site (saved fetch): 4 pairs (EURUSD/GBPUSD/USDJPY/USDCAD), 22-yr backtests win 75–88%, PF 1.3–1.7, "WallStreet Recovery PRO" product, live myfxbook widget IDs 11258834/10397065/11140171/10254966/10498422/10397040.

## Blocks encountered
- DDG html+lite: captcha. Bing HTML+RSS: bot-decoy results. FPA (forexpeacearmy.com), BabyPips, myfxbook member page, dailyforex: 403/Cloudflare. MQL5 search: JS-only. wayback FPA review: no snapshot (availability API: {}).

## Follow-up options (if user wants)
- Try more search sources (Mojeek/Startpage/SEARXNG local) for FPA WallStreet review text.
- Verify EA Automatic landing page content via browser automation (JS SPA).
