# Deep Research: Open-Source Python Trading Tools for quant_os

**Generated**: 2026-07-25
**Researcher**: researcher agent
**Scope**: Every open-source Python trading tool quant_os doesn't already use

---

## Current quant_os Inventory

### Already in `pyproject.toml` (core deps)
| Library | Status |
|---------|--------|
| pandas, numpy, duckdb, sqlalchemy, redis, httpx, websockets | Core runtime |
| fastapi, uvicorn | API server |
| pydantic, structlog, tenacity, orjson | Infrastructure |
| python-dateutil | Date handling |

### Already in optional-deps or codebase
| Library | Where Used | Notes |
|---------|-----------|-------|
| yfinance | `docker/paper_executor.py`, `data_pipeline/sources/market_data.py` | Optional dep |
| scikit-learn | `scripts/train_*.py` (dozens of files) | Optional dep (`ml`) |
| xgboost | `scripts/train_*.py`, `scripts/wf_patched.py` | Optional dep (`ml`) |
| lightgbm | `scripts/train_mega_model*.py` | Used alongside XGBoost |
| optuna | `core/hyperopt.py`, `scripts/train_*.py` | Hyperparameter tuning |
| scipy (stats + optimize) | `scripts/`, `risk/cvar_optimizer.py` | Statistical tests + CVaR |
| matplotlib | `scripts/optuna_tune.py` | Optional dep (`charting`) |
| plotly | `gold_bot/dashboard.py` | Used in Streamlit dashboard |
| streamlit | `gold_bot/dashboard.py` | Gold bot dashboard |
| prometheus_client | `monitoring/metrics_exporter.py` | Metrics export |
| celery | `tasks.py` (via freebuff) | Task scheduling |
| MetaTrader5 | `download_mt5.py`, `download_mt5_symbols.py` | Optional dep (`mt5`) |
| fredapi | `core/data/fred_client.py` | Optional dep (`fred`) |
| pyarrow | Optional dep (`arrow`) | Columnar format |
| **Custom TA indicators** | `tests/test_ema_rsi.py`, `tests/diagnostic_mrb.py`, scripts | Own RSI, EMA, Bollinger, ADX, SMC/ICT detectors |

---

## Every Tool quant_os Does NOT Yet Use

Legend:
- 🔴 **ALREADY HAS** = duplicative, skip
- 🟡 **NICE TO HAVE** = medium value, add when bandwidth available
- 🟢 **HIGH VALUE** = should add soon
- ⭐ **GAME CHANGER** = highest priority

---

# 1. BACKTESTING

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 1.1 | **vectorbt** | `vectorbt` | Vectorized backtesting at scale. Hyperparameter optimization, indicator factory, portfolio-level analysis. Uses NumPy/Pandas broadcasting for O(1) parameter sweeps. | 🔴 NOT USED | MEDIUM | 7/10 |
| 1.2 | **nautilus_trader** | `nautilus-trader` v1.230 | Production-grade Rust-native trading engine. Deterministic event-driven architecture. Supports 20+ brokers/crypto. Actor-based concurrency. Real C++/Rust performance core. | 🔴 NOT USED | HIGH | 8/10 |
| 1.3 | **backtrader** | `backtrader` v1.9.78 | Classic event-driven backtesting framework. Huge ecosystem, cerebello architecture. Last release Apr 2023 (maintenance mode). | 🔴 NOT USED | MEDIUM | 5/10 |
| 1.4 | **zipline-reloaded** | `zipline-reloaded` v3.1.1 | Quantopian's Zipline maintained fork. Pipeline API, alpha factors, event-driven. Strong data bundling. | 🔴 NOT USED | HIGH | 5/10 |
| 1.5 | **bt** | `bt` | Flexible backtesting for Python. Tree-structured strategy composition. Combines alphas like a portfolio. | 🔴 NOT USED | LOW | 4/10 |

**Analysis**: quant_os has its own custom backtesting engine (`backtest/` module, `validation/walk_forward.py`, `scripts/walk_forward.py`). None of the above are drop-in replacements. However, **nautilus_trader** would be the highest-value addition — its Rust-native event engine could replace the custom execution simulation layer for backtesting, and its broker adapters would give quant_os 20+ exchange integrations for free.

---

# 2. DATA PROVIDERS

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 2.1 | **ccxt** | `ccxt` v4.5.68 | Unified API for 100+ crypto exchanges. OHLCV, orderbook, trading. Both sync and async. Pro version has WebSocket streams. | 🔴 NOT USED | LOW | ⭐ 9/10 |
| 2.2 | **alpaca-py** | `alpaca-py` v0.43 | Official Alpaca Markets SDK. Stocks/options/crypto data, paper & live trading. WebSocket real-time. Commission-free API. | 🔴 NOT USED | LOW | 8/10 |
| 2.3 | **polygon-api-client** | `polygon-api-client` v1.16 | Official Polygon.io client. REST + WebSocket. Stocks, options, forex, crypto. Real-time & historical. Enterprise-grade market data. | 🔴 NOT USED | LOW | 8/10 |
| 2.4 | **ib_insync** | `ib-insync` v0.9.86 | Interactive Brokers sync/async Python framework. Market data, orders, portfolio, scanner. Most popular IB Python lib. | 🔴 NOT USED | MEDIUM | 7/10 |

**Analysis**: ccxt is a MASSIVE gap. quant_os trades XAUUSD on MT5 but has zero crypto capability. With ccxt, the whole crypto market opens up (100+ exchanges). Alpaca and Polygon would give US equities/options. ib_insync would unlock Interactive Brokers. All are low-effort pip installs.

---

# 3. TECHNICAL ANALYSIS

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 3.1 | **pandas-ta** | `pandas-ta` v0.4.71b | 130+ indicators as Pandas DataFrame extensions. RSI, MACD, Ichimoku, Renko, Heikin-Ashi, all built on TA-Lib concepts but pure Python. | 🔴 NOT USED | LOW | ⭐ 9/10 |
| 3.2 | **TA-Lib** | `TA-Lib` v0.7.1 | Industry-standard C library with Python wrapper. 150+ indicators. Battle-tested for 20+ years. Fastest TA calculations. | 🔴 NOT USED | MEDIUM | 7/10 |
| 3.3 | **ta** | `ta` | Pure Python TA library. Simpler API than pandas-ta. Trend, momentum, volume, volatility indicators. | 🔴 NOT USED | LOW | 5/10 |
| 3.4 | **finta** | `finta` | Financial Technical Analysis. Clean API, pure Python. Supports 80+ indicators. | 🔴 NOT USED | LOW | 5/10 |

**Analysis**: quant_os currently rolls its own RSI, EMA, Bollinger, ADX, and SMC/ICT detectors from scratch. This is error-prone and unmaintainable. **pandas-ta** is the clear winner — 130+ indicators as `df.ta.rsi()` extension, pure Python (no C compilation), actively maintained. TA-Lib has more indicators and is faster, but requires C library installation (pain on Windows/Wine). Strong recommendation: adopt pandas-ta as the official indicator library and deprecate custom implementations.

---

# 4. ML / STATISTICS

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 4.1 | **statsmodels** | `statsmodels` v0.14.6 | Statistical models: ARIMA, GARCH, VAR, cointegration, Granger causality, regression diagnostics. Gold standard for econometrics. | 🔴 NOT USED | LOW | ⭐ 9/10 |
| 4.2 | **prophet** | `prophet` | Facebook/Meta time series forecasting. Handles seasonality, holidays, changepoints. Bayesian structural time series. | 🔴 NOT USED | LOW | 6/10 |
| 4.3 | **statsforecast** | `statsforecast` | Nixtla's fast statistical forecasting. AutoARIMA, ETS, CES, Theta. Orders of magnitude faster than statsmodels for forecasting. | 🔴 NOT USED | LOW | 7/10 |
| 4.4 | **catboost** | `catboost` | Yandex gradient boosting. Better with categorical features. Often beats XGBoost/LightGBM on financial data with mixed types. | 🔴 NOT USED | LOW | 7/10 |

**Analysis**: statsmodels is a glaring omission. quant_os does regression and ML but has no proper econometrics — no ADF stationarity tests, no cointegration, no GARCH volatility modeling. statsmodels adds all of this in one pip install. Prophet/statsforecast would augment the time series forecasting pipeline. Catboost would give a third ensemble option alongside the existing XGBoost/LightGBM.

---

# 5. PORTFOLIO OPTIMIZATION

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 5.1 | **PyPortfolioOpt** | `PyPortfolioOpt` | Markowitz mean-variance, Black-Litterman, HRP, risk parity. Industry standard for portfolio construction in Python. | 🔴 NOT USED | LOW | ⭐ 9/10 |
| 5.2 | **Riskfolio-Lib** | `Riskfolio-Lib` | Advanced portfolio optimization. 10+ risk measures (CVaR, CDaR, MAD, etc.), HRP, HERC, NCO. Built on cvxpy. | 🔴 NOT USED | LOW | ⭐ 9/10 |
| 5.3 | **cvxpy** | `cvxpy` v1.9.2 | Convex optimization DSL. Underpins PyPortfolioOpt and Riskfolio-Lib. General-purpose for any convex problem. | 🔴 NOT USED | MEDIUM | 7/10 |

**Analysis**: quant_os has `risk/cvar_optimizer.py` with scipy.optimize but no proper portfolio construction framework. PyPortfolioOpt would immediately give Markowitz, Black-Litterman, and HRP. Riskfolio-Lib adds CVaR, CDaR, and hierarchical methods. Together they'd transform quant_os from single-strategy trading to multi-asset portfolio management. Both are pip-installable, pure Python.

---

# 6. VISUALIZATION

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 6.1 | **mplfinance** | `mplfinance` v0.12.10b | Candlestick charts, volume overlays, technical indicators on matplotlib. Built for financial data viz. | 🔴 NOT USED | LOW | 8/10 |
| 6.2 | **dash** | `dash` | Plotly's web dashboard framework. Interactive, reactive, production-grade. Python-only (no JS needed). | 🔴 NOT USED | MEDIUM | 6/10 |
| 6.3 | **bokeh** | `bokeh` | Interactive visualization for web browsers. Server-push architecture. Better for streaming data than dash. | 🔴 NOT USED | MEDIUM | 5/10 |

**Analysis**: quant_os already has matplotlib (optional), plotly, and streamlit. However, **mplfinance** would be a significant quality-of-life upgrade for candlestick/research charts. Dash would be redundant with the existing Streamlit dashboard. Bokeh is better for streaming real-time data but adds complexity.

---

# 7. PRODUCTION / INFRASTRUCTURE

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 7.1 | **celery** | `celery` | Distributed task queue. Already partially used in `tasks.py` (freebuff). | 🟡 PARTIAL | LOW | 8/10 |
| 7.2 | **prometheus_client** | `prometheus_client` | Metrics exposition for Prometheus. Already in `monitoring/metrics_exporter.py`. | 🟡 ALREADY USED | — | — |
| 7.3 | **grafana** | (Docker) | Dashboard for Prometheus metrics. Already in docker-compose.yml. | 🟡 ALREADY USED | — | — |
| 7.4 | **redis** | `redis` v5.0 | Already in core deps. Used for caching/pubsub. | 🟡 ALREADY USED | — | — |

**Analysis**: quant_os already has the production stack (Redis, Celery, Prometheus, Grafana, FastAPI). No major gaps here. Consider formalizing Celery into the official deps list (currently only in tasks.py).

---

# 8. QUANT FINANCE

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 8.1 | **OpenBB Terminal** | `openbb` v4.7.2 | Bloomberg Terminal replacement. 100+ data providers, AI agents, Excel add-in, REST API. Massive ecosystem. | 🔴 NOT USED | HIGH | 7/10 |
| 8.2 | **QuantLib-Python** | `QuantLib-Python` v1.18 | Industry-standard quantitative finance. Options pricing (Black-Scholes, binomial trees), yield curves, fixed income, credit. C++ backend. | 🔴 NOT USED | HIGH | 6/10 |
| 8.3 | **finmarketpy** | `finmarketpy` | Backtesting + market data for FX, rates, and vol. Built by a bank quant. | 🔴 NOT USED | MEDIUM | 5/10 |

**Analysis**: OpenBB is impressive but heavy — it's a full terminal, not a library. If quant_os needs a research/data aggregation layer, OpenBB's provider abstraction could be useful. QuantLib is only valuable if quant_os expands into options/fixed income (currently pure spot FX). Both are high-effort integrations.

---

# 9. NEWS / SENTIMENT

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 9.1 | **transformers** | `transformers` v5.14 | HuggingFace transformers. FinBERT, BERT, RoBERTa. Text classification for sentiment. State-of-the-art NLP. | 🔴 NOT USED | HIGH | 6/10 |
| 9.2 | **vaderSentiment** | `vaderSentiment` | Rule-based sentiment for social media/finance. No GPU needed. Fast, lightweight. | 🔴 NOT USED | LOW | 7/10 |
| 9.3 | **textblob** | `textblob` | Simple NLP: sentiment, POS tagging, NP extraction. Good enough for basic news sentiment. | 🔴 NOT USED | LOW | 5/10 |
| 9.4 | **finbert** (via transformers) | `transformers` | ProsusAI/finBERT — BERT fine-tuned on financial text. Best for earnings, news, filings. | 🔴 NOT USED | HIGH | 8/10 |

**Analysis**: quant_os has news/events infrastructure (`news_events/` module) and `data_pipeline/sources/news_sentiment.py` but no actual NLP model. vaderSentiment is a quick win — rule-based, no GPU, instantly adds sentiment scoring to news/social feeds. finBERT via transformers would give state-of-the-art financial sentiment but requires GPU and larger dependency overhead. Also of note: both textblob and vaderSentiment appear in the `.freebuff` worktree but not in the main codebase.

---

# 10. OPTIMIZATION

| # | Name | PyPI | What It Does | Status | Effort | Value |
|---|------|------|-------------|--------|--------|-------|
| 10.1 | **nevergrad** | `nevergrad` | Facebook/Meta derivative-free optimization. 100+ algorithms. For anything non-differentiable (trading strategy params, risk budgets). | 🔴 NOT USED | LOW | 8/10 |
| 10.2 | **cvxpy** | (see §5.3) | Convex optimization. Already covered in portfolio section. | 🔴 NOT USED | MEDIUM | 7/10 |
| 10.3 | **scipy.optimize** | `scipy` | Already used in `risk/cvar_optimizer.py` for CVaR optimization. | 🟡 ALREADY USED | — | — |
| 10.4 | **optuna** | `optuna` | Already used extensively in `core/hyperopt.py` and `scripts/train_*.py`. TPE sampler, median pruner. | 🟡 ALREADY USED | — | — |

**Analysis**: nevergrad would complement optuna. While optuna excels at hyperparameter tuning with tree-structured search spaces, nevergrad's strength is derivative-free optimization for noisy objective functions — perfect for strategy parameter optimization where the fitness landscape is non-smooth.

---

# 🏆 TOP 10 PRIORITY ADDITIONS (Ranked by Value/Effort)

| Rank | Library | Category | Value | Effort | Why |
|------|---------|----------|-------|--------|-----|
| **1** | **pandas-ta** | TA | 9/10 | LOW | Replace custom RSI/EMA/Bollinger implementations with 130+ battle-tested indicators. One-line `pip install`. |
| **2** | **ccxt** | Data | 9/10 | LOW | Unlock 100+ crypto exchanges. Low effort, massive market expansion. |
| **3** | **statsmodels** | ML/Stats | 9/10 | LOW | Add proper econometrics — ADF, cointegration, GARCH. Quant finance essential. |
| **4** | **PyPortfolioOpt** | Portfolio | 9/10 | LOW | Markowitz + Black-Litterman + HRP in one pip install. Elevates to multi-asset. |
| **5** | **Riskfolio-Lib** | Portfolio | 9/10 | LOW | Advanced risk measures (CVaR, CDaR, MAD). Hierarchical methods. |
| **6** | **vaderSentiment** | Sentiment | 7/10 | LOW | Instant news/social sentiment. No GPU, no model downloads. |
| **7** | **alpaca-py** | Data | 8/10 | LOW | US equities + options trading via Alpaca. Commission-free paper trading. |
| **8** | **nevergrad** | Optimization | 8/10 | LOW | Derivative-free optimization for noisy objective functions. Complements optuna. |
| **9** | **nautilus_trader** | Backtesting | 8/10 | HIGH | Rust-native engine. 20+ broker adapters. Production-grade backtesting. |
| **10** | **mplfinance** | Visualization | 8/10 | LOW | Candlestick charts, indicator overlays on matplotlib. Research upgrade. |

---

## Integration Strategy

### Phase 1 — Quick Wins (this sprint)
```
pip install pandas-ta ccxt statsmodels vaderSentiment
```
- Replace custom TA with `pandas-ta` (backward-compatible wrapper)
- Add `ccxt` as optional dep `[crypto]` for crypto data
- Wire `statsmodels` into validation pipeline (ADF, cointegration tests)
- Add `vaderSentiment` to news_sentiment pipeline

### Phase 2 — Portfolio Upgrade (next sprint)
```
pip install PyPortfolioOpt Riskfolio-Lib nevergrad
```
- Build portfolio construction module using PyPortfolioOpt
- Add Riskfolio-Lib for CVaR optimization (replacing/supplementing custom `cvar_optimizer.py`)
- Use nevergrad alongside optuna for strategy param optimization

### Phase 3 — Production Backtesting (future)
```
pip install nautilus-trader
```
- Evaluate nautilus_trader as backtesting engine replacement
- Leverage its broker adapters for multi-venue execution

### Phase 4 — Multi-Asset Expansion (future)
```
pip install alpaca-py polygon-api-client ib-insync
```
- Add equities/options data sources
- Enable multi-asset portfolio trading

---

## Libraries NOT Recommended

| Library | Reason |
|---------|--------|
| **backtrader** | Maintenance mode since 2023. quant_os has better custom backtesting. |
| **zipline-reloaded** | Heavy, Quantopian legacy. Overkill for spot FX. |
| **bt** | Too simple. Does less than quant_os's existing backtesting. |
| **QuantLib-Python** | Only if expanding to options/fixed income. Heavy C++ dependency. |
| **OpenBB Terminal** | Full terminal, not a library. Overlap with existing Streamlit dashboards. |
| **finmarketpy** | Niche, low community. Less than pandas-ta + statsmodels combined. |
| **ta** / **finta** | Both do less than pandas-ta. No reason to choose over pandas-ta. |
| **TA-Lib** | Faster but requires C compilation. pandas-ta is pure Python, more indicators. |
| **dash** / **bokeh** | Redundant with existing Streamlit + Plotly dashboard. |
| **prophet** | Heavy (pystan), overkill for FX. statsforecast does similar with less overhead. |
| **finBERT** (transformers) | Requires GPU + ~2GB model. vaderSentiment does 80% of the job with 0 cost. |

---

*This report was generated by the researcher agent. Findings are evidence-based from codebase scanning and PyPI research. Accuracy: HIGH. Confidence: 0.9.*
