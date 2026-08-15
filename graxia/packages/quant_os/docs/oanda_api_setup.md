# Oanda API Setup — Practice Account

## Why Oanda?

- Best forex CFD data (real-time bid/ask, not mid-price)
- Free practice account with full API access
- Covers: Forex, Metals (XAU/USD, XAG/USD), Indices (US30, NAS100)
- REST API v3 with candles, account info, pricing

## Step-by-Step Setup

### 1. Create Practice Account (if not already)

1. Go to https://www.oanda.com/account/practice/
2. Sign up with email
3. Complete registration
4. Note your **Account ID** (format: `1715547844-001`)

### 2. Generate API Token

1. Go to https://www.oanda.com/account/api-access/
2. Login with your practice account
3. Click **"Generate Token"** (or "Create API Token")
4. Set a descriptive name: `quant_os_dev`
5. **Copy the token immediately** (shown only once!)

### 3. Configure in `.env`

```bash
# Oanda (Forex/CFD broker + data)
OANDA_ACCESS_TOKEN=<paste-your-token-here>
OANDA_ACCOUNT_ID=1715547844
OANDA_ENVIRONMENT=Practice
```

### 4. Test Connection

```python
import os
from market_data.providers import DataProviders, OandaConfig, OandaProvider

providers = DataProviders.from_env()
bars = providers.get_forex_bars("EURUSD", "1h", "2025-01-01", "2025-01-31")
print(f"Got {len(bars)} EURUSD H1 bars from Oanda")
providers.close()
```

Or via CLI:
```bash
python -c "from market_data.providers import DataProviders; p=DataProviders.from_env(); print(p.health_check()); p.close()"
```

## Oanda API Limits

| Tier | Rate Limit | Data |
|------|------------|------|
| Practice | 120 req/min | Real-time |
| Live | 120 req/min | Real-time |

## Instruments Available

| Type | Examples |
|------|----------|
| Forex | EUR_USD, GBP_USD, USD_JPY, AUD_USD |
| Metals | XAU_USD, XAG_USD |
| CFDs | US30_USD, NAS100_USD, SPX500_USD |
| Crypto | BTC_USD (if enabled) |

## Troubleshooting

- **401 Unauthorized**: Token expired or wrong — regenerate
- **403 Forbidden**: Account not funded (practice accounts auto-fund)
- **429 Rate Limited**: Wait 60s, reduce request frequency
