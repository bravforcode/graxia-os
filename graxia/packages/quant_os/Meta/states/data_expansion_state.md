# Data Expansion State

**Date:** 2026-06-26
**Session:** Full data expansion to 9 TFs + ticks + news/macro

## Step 1 — Mega Download (9 TFs)

Ran `scripts/mega_download.py --direct` (full, not quick).
M1 and M5 failed at 100K bars (`Terminal: Invalid params`).
Re-downloaded M1/M5 with 5K bar limit — all succeeded.

### Final per-symbol TF coverage

| Symbol  | TFs |
|---------|-----|
| EURUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| GBPUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| USDJPY  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| AUDUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| USDCAD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| USDCHF  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| NZDUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| XAUUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| XAGUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| XPTUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| XPDUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| US30    | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| NAS100  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| BTCUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |
| ETHUSD  | M1, M5, M15, M30, H1, H4, D1, W1, MN1 |

**15 symbols × 9 TFs = 135 CSV files**

## Step 2 — Data Inventory

- **Total CSV files:** 135
- **Total size:** 162.8 MB
- **Estimated bars:** 2,952,097

M1/M5 note: Each limited to 5,000 bars (MT5 terminal limit). All other TFs at max bars (M15: 60K, M30: 50K, H1: 50K, H4: 25K, D1: 5K, W1: 2K, MN1: 1K).

## Step 3 — Tick Data

Ran `scripts/download_ticks_and_news.py`:
- **XAUUSD:** 733,743 ticks (24h)
- **EURUSD:** 408,861 ticks (24h)
- **US30:** 193,789 ticks (24h)
- **GBPUSD:** 622,772 ticks (24h)
- **USDJPY:** 386,245 ticks (24h)
- **BTCUSD:** failed (intermittent MT5 symbol_select issue)
- **Total: 2,345,410 ticks** from 5 symbols

Format: Parquet, stored in `data/ticks/`.

## Step 4 — News / Macro

Ran same script — uses cloudscraper to bypass Cloudflare:
- **ForexFactory:** 98 calendar events (`data/news/forexfactory_calendar.json`)
- **Investing.com:** 49 economic events (`data/news/investing_calendar.json`)
- Both sources include time, currency, event name, importance, actual/forecast/previous

## Errors & Notes

- M1/M5: 100K bar limit failed with `Terminal: Invalid params`. Workaround: 5K bars.
- BTCUSD ticks: Intermittently fails symbol_select (MT5 connection timing).
- First `--direct` run timed out after 10 min (too many large TF downloads).
- Cleaned up 5 stale files (TEST, multi_symbol_log, paper_trade_log, old MN files).

## Files Modified/Created

| File | Action |
|------|--------|
| `data/*.csv` (135 files) | Created/refreshed |
| `data/ticks/*.parquet` (5 files) | Created |
| `data/news/*.json` (2 files) | Created |
| `scripts/download_ticks_and_news.py` | Created |
| `scripts/check_data.py` | Created |
| `scripts/mega_download.py` | Unchanged |
| `Meta/data_manifest.json` | Refreshed (from scan) |
