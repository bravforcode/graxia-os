# TradingView + PixelRAG Integration Guide

## Overview

quant_os now integrates three powerful data sources:

| Component | What it does | How it connects |
|-----------|-------------|-----------------|
| **TradingView MCP** | Market data, screening, backtest, sentiment | HTTP API to MCP server |
| **TradingView CDP** | Chart control, Pine Script, drawing tools | Chrome DevTools Protocol |
| **PixelRAG** | Visual search over charts and reports | FAISS index + visual embeddings |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  quant_os API (FastAPI)                                      │
│                                                              │
│  /tradingview/* ──► TradingViewClient ──► MCP Server         │
│  /visual/*      ──► VisualChartSearch ──► PixelRAG Server    │
│  /cdp/*         ──► TradingViewCDP    ──► Chrome CDP         │
│                                                              │
│  core/tv_integration.py (TradingOrchestrator)                │
│    ├── full_analysis()        — all sources combined         │
│    ├── auto_backtest()        — cross-validation + screenshot│
│    ├── screen_and_analyze()   — screen → analyze top N       │
│    ├── chart_pattern_search() — visual RAG search            │
│    └── auto_pine_workflow()   — generate → compile → index   │
└─────────────────────────────────────────────────────────────┘
```

## Setup

### 1. TradingView MCP (Market Data)

```powershell
# Install uv
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install TradingView MCP
uv tool install --python 3.13 tradingview-mcp-server

# Set env var (optional, defaults to localhost:30001)
$env:TV_MCP_URL = "http://localhost:30001"
```

### 2. PixelRAG (Visual Search)

```powershell
# Install PixelRAG
pip install "pixelrag[serve]"

# Build index from your reports/charts
pixelrag index build

# Serve the index
pixelrag serve --index-dir ./data/visual_index --port 30001

# Set env var (optional)
$env:PIXELRAG_URL = "http://localhost:30001"
```

### 3. TradingView CDP (Chart Control)

```powershell
# Launch TradingView Desktop with debug port
Start-Process "TradingView.exe" -ArgumentList "--remote-debugging-port=9222"

# OR launch Chrome with TradingView
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\chrome-debug" `
  https://www.tradingview.com

# Set env var (optional)
$env:TV_CDP_URL = "http://localhost:9222"
```

## API Endpoints

### TradingView — `/tradingview`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tradingview/snapshot` | Market snapshot (S&P500, BTC, VIX, Gold, DXY) |
| GET | `/tradingview/price/{symbol}` | Real-time price |
| GET | `/tradingview/ohlcv/{symbol}` | OHLCV candles |
| GET | `/tradingview/screen/{exchange}` | Screen stocks/crypto |
| POST | `/tradingview/backtest/{symbol}` | Run backtest |
| GET | `/tradingview/sentiment/{symbol}` | Reddit + news sentiment |
| GET | `/tradingview/analyze/{symbol}` | Full analysis |

### Visual Search — `/visual`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/visual/index/chart` | Index a chart image |
| POST | `/visual/index/url` | Index a web page |
| POST | `/visual/index/directory` | Index all files in directory |
| POST | `/visual/search/text` | Search by text query |
| POST | `/visual/search/image` | Search by image similarity |
| GET | `/visual/index/stats` | Index statistics |
| POST | `/visual/index/build` | Build FAISS index |
| POST | `/visual/serve` | Start PixelRAG server |

### CDP — `/cdp`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cdp/symbol` | Get current chart symbol |
| POST | `/cdp/symbol/{symbol}` | Change chart symbol |
| POST | `/cdp/timeframe/{timeframe}` | Change timeframe |
| POST | `/cdp/draw/support` | Draw support line |
| POST | `/cdp/draw/resistance` | Draw resistance line |
| POST | `/cdp/pine/write` | Write Pine Script |
| POST | `/cdp/pine/compile` | Compile Pine Script |
| POST | `/cdp/layout/{layout}` | Set chart layout |
| POST | `/cdp/screenshot` | Take chart screenshot |

## Usage Examples

### Python — Full Analysis

```python
from core.tv_integration import TradingOrchestrator

orch = TradingOrchestrator()
insight = await orch.full_analysis("XAUUSD")
print(f"Recommendation: {insight.recommendation} ({insight.confidence:.0%})")
print(f"Price: {insight.price_data}")
print(f"Sentiment: {insight.sentiment}")
print(f"Visual matches: {len(insight.visual_matches)}")
```

### Python — Screen and Analyze

```python
# Screen oversold crypto, analyze top 5
insights = await orch.screen_and_analyze(
    exchange="BINANCE", screener="oversold", top_n=5
)
for i in insights:
    print(f"{i.symbol}: {i.recommendation} ({i.confidence:.0%})")
```

### Python — Auto Backtest

```python
# Cross-validate RSI strategy
comparison = await orch.auto_backtest_workflow("AAPL", strategy="rsi")
print(f"TradingView: {comparison.tv_result}")
print(f"Divergence: {comparison.divergence}")
```

### Python — Chart Pattern Search

```python
# Search for charts with specific patterns
results = await orch.chart_pattern_search("head and shoulders pattern")
for r in results:
    print(f"Score: {r['score']:.2f} — {r['snippet']}")
```

### Python — Auto Pine Script

```python
# Generate → compile → backtest → screenshot → index
result = await orch.auto_pine_workflow("AAPL", {
    "name": "MyRSI",
    "length": 14,
    "overbought": 70,
    "oversold": 30,
})
print(f"Compiled: {result.compile_result.success}")
print(f"Indexed: {result.indexed}")
```

### curl — Quick Commands

```bash
# Market snapshot
curl http://localhost:8000/tradingview/snapshot

# Screen oversold NASDAQ
curl http://localhost:8000/tradingview/screen/NASDAQ?screener=oversold

# Backtest RSI on AAPL
curl -X POST http://localhost:8000/tradingview/backtest/AAPL?strategy=rsi

# Search charts by text
curl -X POST "http://localhost:8000/visual/search/text?query=double+top"

# Draw support line
curl -X POST "http://localhost:8000/cdp/draw/support?price=2300"
```

## Configuration

All settings are environment-variable driven with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `TV_MCP_URL` | `http://localhost:30001` | TradingView MCP server URL |
| `TV_DEFAULT_TIMEFRAME` | `1D` | Default candle timeframe |
| `TV_SCREEN_EXCHANGE` | `NASDAQ` | Default screening exchange |
| `PIXELRAG_URL` | `http://localhost:30001` | PixelRAG server URL |
| `PIXELRAG_INDEX_DIR` | `data/visual_index` | FAISS index directory |
| `PIXELRAG_TILES_DIR` | `data/visual_tiles` | Screenshot tiles directory |
| `TV_CDP_URL` | `http://localhost:9222` | CDP endpoint URL |
| `TV_CDP_TIMEOUT` | `30` | CDP connection timeout (seconds) |
| `TV_CDP_CHROME_PATH` | (auto-detect) | Chrome executable path |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| TradingView MCP shows failed | Run `tradingview-mcp.exe` from PowerShell, restart Claude Desktop |
| CDP can't connect | Ensure TradingView/Chrome launched with `--remote-debugging-port=9222` |
| PixelRAG returns empty | Check `pixelrag serve` is running on correct port |
| Visual search returns no results | Run `pixelrag index build` first |
| Pine Script compile fails | Check TradingView Pine Editor for syntax errors |

## Files Created

```
quant_os/
├── api/
│   ├── tv_client.py          # TradingView MCP client (555 lines)
│   ├── tv_cdp.py             # TradingView CDP bridge (960 lines)
│   ├── tv_routes.py          # TradingView API routes (317 lines)
│   ├── visual_routes.py      # Visual search API routes (268 lines)
│   └── cdp_routes.py         # CDP API routes (226 lines)
├── analysis/
│   └── visual_search.py      # PixelRAG visual search (669 lines)
├── config/
│   ├── tv_config.py          # TradingView MCP config
│   ├── pixelrag_config.py    # PixelRAG config
│   └── tv_cdp_config.py      # CDP config
├── core/
│   └── tv_integration.py     # TradingOrchestrator (514 lines)
└── tests/
    ├── test_tv_integration.py # Unit tests (571 lines)
    └── test_api_routes.py     # API route tests
```

## Running Tests

```bash
# All integration tests
python -m pytest tests/test_tv_integration.py -v

# API route tests
python -m pytest tests/test_api_routes.py -v

# Both
python -m pytest tests/test_tv_integration.py tests/test_api_routes.py -v
```
