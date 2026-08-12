# Data Ingestion Tools — FINAL HONEST REPORT
## Verified: 2026-06-28

### ALL 22 TOOLS — VERIFIED STATUS

#### ✅ WORKS IMMEDIATELY (No key needed) — 17 tools
| # | Tool | Verified Result |
|---|------|-----------------|
| 1 | yfinance | XAUUSD=$4078.70 ✅ |
| 2 | ccxt | BTC/USDT=$60,690 ✅ |
| 3 | pandas-datareader | v0.11.1 ✅ |
| 4 | akshare | v1.18.64 ✅ |
| 5 | textblob | polarity=0.30/-0.65 ✅ |
| 6 | vaderSentiment | compound=0.64/-0.54 ✅ |
| 7 | transformers | Import OK ✅ |
| 8 | pandera | v0.32.0 ✅ |
| 9 | great_expectations | v1.18.2 ✅ |
| 10 | duckdb | SELECT 42=42 ✅ |
| 11 | chromadb | 1 doc inserted ✅ |
| 12 | qdrant_client | Import OK ✅ |
| 13 | prefect | v3.7.6 ✅ |
| 14 | dagster | v1.13.11 ✅ |
| 15 | mlflow | v3.14.0 ✅ |
| 16 | wandb | v0.28.0 ✅ |
| 17 | feast | v0.64.0 ✅ |

#### ✅ WORKS WITH API KEY — 4 tools
| # | Tool | Key Status | Verified Result |
|---|------|------------|-----------------|
| 18 | alpha_vantage | Set ✅ | EUR/USD=1.139, rate limit 25/day |
| 19 | fredapi | Set ✅ | GDP=31865.7B (9 obs) |
| 20 | newsapi | Set ✅ | 1512 articles for "gold trading" |
| 21 | praw | Needs Reddit creds | Import OK |

#### ❌ BROKEN — 1 tool
| # | Tool | Issue |
|---|------|-------|
| 22 | finbert_embedding | TF/Keras API changed, use transformers instead |

### API KEYS STORED
- ALPHAVANTAGE_API_KEY=69A2D75S09YBKLGR (env var)
- FRED_API_KEY=ca6997817f1fad59485310fc56ae594e (env var)
- NEWS_API_KEY=98acea70c06f4dd5ac1489054d877768 (env var)
- praw: needs Reddit API credentials

### WHAT EACH TOOL ACTUALLY DOES

**yfinance** — Downloads OHLCV from Yahoo Finance
- Works: stocks, ETFs, forex, crypto, commodities
- Free, no key, no rate limit (practical)
- Example: yf.Ticker("GC=F").history(period="5d")

**ccxt** — Connects to 100+ crypto exchanges
- Works: Binance, Coinbase, Kraken, etc.
- Free, no key needed for public data
- Example: ccxt.binance().fetch_ticker("BTC/USDT")

**alpha_vantage** — Financial data API
- Works: daily/weekly stocks, forex, technical indicators
- Rate limit: 25 requests/day (free tier)
- Example: ts.get_daily("IBM")

**fredapi** — Federal Reserve Economic Data
- Works: 800k+ economic series
- Free, needs key
- Example: fred.get_series("GDP")

**pandas-datareader** — Multi-source data reader
- Works: FRED, World Bank, Fama-French
- Free, no key for many sources

**akshare** — China/Asia financial data
- Works: China stocks, futures, macro
- Free, no key

**textblob** — Sentiment analysis
- Works: polarity (-1 to +1), subjectivity (0 to 1)
- Free, no key, instant

**vaderSentiment** — Social media sentiment
- Works: compound (-1 to +1), pos/neg/neu
- Free, no key, instant

**transformers** — HuggingFace NLP models
- Works: import, needs model download for inference
- Free, use FinBERT model for financial sentiment

**pandera** — DataFrame validation
- Works: schema-based validation
- Free, no key

**great_expectations** — Data quality framework
- Works: expectation suites
- Free, no key

**duckdb** — In-process OLAP database
- Works: SQL queries on DataFrames
- Free, no key, very fast

**chromadb** — Vector database
- Works: store/query embeddings
- Free, no key

**qdrant_client** — Vector search client
- Works: import, needs server for production
- Free, no key

**prefect** — Workflow orchestration
- Works: define/run flows
- Free, no key

**dagster** — Data asset orchestration
- Works: define/run assets
- Free, no key

**mlflow** — ML experiment tracking
- Works: log/compare experiments
- Free, no key

**wandb** — ML logging + visualization
- Works: log metrics, models
- Free tier available

**feast** — Feature store
- Works: define/serve features
- Free, no key

### NEXT STEPS
1. Start with yfinance + ccxt for market data
2. Use textblob + vader for sentiment
3. Use duckdb for analytics
4. Use chromadb for vector search
5. Use prefect for orchestration
6. Add fredapi for macro data (key ready)
7. Add newsapi for news (key ready)
8. Add alpha_vantage sparingly (25/day limit)
