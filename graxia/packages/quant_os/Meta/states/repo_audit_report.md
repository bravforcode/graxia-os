# 🔍 Deep Dive Audit: 27 Trading Bot Repositories

> **Audit Date**: 2026-06-26
> **Auditor**: bridge agent (RUFLOW)
> **Methodology**: Fetched each repo, analyzed README, structure, stars, commits, last update, license, code quality indicators
> **Verdict per repo**: Honest assessment — no hype, no sugarcoating

---

## 📊 Summary Scorecard

| # | Repo | Stars | Commits | Last Active | Language | Verdict | Usefulness for Graxia |
|---|------|-------|---------|-------------|----------|---------|----------------------|
| 1 | zero-was-here/tradingbot | 116 | 6 | Recent | Python | ⚠️ Hype-heavy | Low — marketing repo, no real code depth |
| 2 | t73liu/trading-bot | 23 | 234 | Active | Go/Python | ✅ Solid | Medium — Go+Python polyglot, good architecture |
| 3 | kvrancic/algorithmic-trading-bot | 5 | 34 | Recent | Python | ✅ Good | High — clean Python, ML pipeline, risk mgmt |
| 4 | freqtrade/freqtrade | 51.9k | 32,141 | Very Active | Python | ✅✅ Production-grade | High — industry standard, but crypto-only |
| 5 | raidastauras/Trading-Bot | 146 | 127 | Active | Python | ✅ Research-grade | Medium — honest research, OANDA integration |
| 6 | Puttipong1234/BOT-TRADE-TUTORIAL | 13 | 18 | Stale | Python | ❌ Tutorial | Low — tutorial repo, not production code |
| 7 | HKUDS/AI-Trader | 20.1k | 388 | Very Active | Python/TS | ⚠️ Platform | Medium — agent-native platform, not a bot |
| 8 | estebanthi/binance-trading-bot | 9 | 109 | Archived | Python | ❌ Archived | Zero — archived Oct 2025, dead |
| 9 | Stefodan21/Forex-trading-bot | 8 | 12 | Recent | Python | ⚠️ Early | Medium — PPO+AMD GPU, but only 12 commits |
| 10 | Hivelancee/Forex-Trading-Robot | — | — | — | — | ❌ 404 | Zero — repo doesn't exist |
| 11 | pkellz/everest | 11 | 51 | Stale (2019) | JS | ❌ Dead | Zero — Poloniex-only, abandoned 2019 |
| 12 | jesse-ai/jesse | 8.1k | 3,372 | Very Active | Python/JS | ✅✅ Production-grade | High — mature framework, good strategy API |
| 13 | emreeldemir/Trading-Bot | 0 | 3 | Recent | Python/JS | ❌ Student project | Zero — 0 stars, 3 commits, coursework |
| 14 | olivierrousselle/Bot-trading-crypto | — | — | — | — | ❌ 404 | Zero — repo doesn't exist |
| 15 | clementpl/influx-crypto-trader | 78 | 135 | Stale | TypeScript | ⚠️ Stale | Low — interesting InfluxDB+Grafana, but abandoned |
| 16 | owini/quant-research | 3 | 124 | Fork | Python | ⚠️ Fork | Low — fork of letianzj/QuantResearch, no original work |
| 17 | mrdarylguy/trading_strategies | 2 | 48 | Active | Python | ⚠️ Scripts | Low — collection of scripts, not a framework |
| 18 | day0market/pyalgotrader | 159 | 15 | Stale | Python | ⚠️ Fork | Low — fork of vnpy, translation quality issues |
| 19 | The-Swarm-Corporation/BackTesterAgent | 14 | 10 | Recent | Python | ⚠️ Wrapper | Low — thin wrapper around Swarms framework |
| 20 | letianzj/quanttrader | 743 | 128 | Stale | Python | ✅ Good | Medium — clean event-driven, IB integration |
| 21 | cyclux/tradeforce | 11 | 170 | Active | Python | ✅ Good | Medium — Numba-accelerated, Docker, Optuna |
| 22 | StateOfTheArt-quant/sharpe | 51 | 77 | Stale | Python | ⚠️ Alpha | Low — early alpha, RL environment, incomplete |
| 23 | EthanAlgoX/LLM-TradeBot | 294 | 439 | Very Active | Python | ⚠️ Over-engineered | Low — too complex, 8 LLM providers, marketing-heavy |
| 24 | tauricresearch/tradingagents | 88.8k | 243 | Very Active | Python | ✅✅ Research-grade | High — academic paper, multi-agent LLM, but research-only |
| 25 | rom1trt/trading-bot | 2 | 31 | Stale | Python | ❌ Tutorial | Zero — personal learning project |
| 26 | FranQuant/AI-based-Trading-Strategies | — | — | — | — | ❌ 404 | Zero — repo doesn't exist |

---

## 🏆 Tier 1: Actually Useful (4 repos)

### 1. freqtrade/freqtrade — ⭐⭐⭐⭐⭐
- **What**: Production-grade crypto trading framework
- **Why useful**: 51.9k stars, 32k commits, active development, Docker support, FreqAI (ML), hyperopt, Telegram control
- **Honest take**: The gold standard for crypto. But it's crypto-only — no forex/stocks. GPL-3.0 license (copyleft). Cannot be used as a library in proprietary code.
- **Graxia fit**: Reference architecture only. Study its plugin system, strategy API, and risk management. Do NOT fork or depend on it.

### 2. jesse-ai/jesse — ⭐⭐⭐⭐
- **What**: Advanced crypto trading framework with simple Python API
- **Why useful**: 8.1k stars, 3.3k commits, clean strategy syntax, built-in ML pipeline, Monte Carlo analysis, JesseGPT
- **Honest take**: Best developer experience in the space. Strategy code is genuinely elegant. But crypto-only, MIT license (good).
- **Graxia fit**: **Best reference for strategy API design**. Study how they define `should_long()`, `go_long()`, risk management helpers. Could inspire Graxia's strategy interface.

### 3. tauricresearch/tradingagents — ⭐⭐⭐⭐
- **What**: Multi-agent LLM trading framework (academic paper)
- **Why useful**: 88.8k stars (!), arXiv paper, multi-provider LLM support, Docker, structured decision pipeline
- **Honest take**: Impressive research project. But it's LLM-dependent (expensive), non-deterministic, and explicitly says "not for real trading." Good for ideas, not for production.
- **Graxia fit**: Study the multi-agent architecture (Analyst Team → Researcher Team → Trader → Risk Management). Do NOT copy the LLM dependency model.

### 4. kvrancic/algorithmic-trading-bot — ⭐⭐⭐
- **What**: Algorithmic trading bot with sentiment analysis and ML
- **Why useful**: Clean Python, XGBoost/LSTM/CNN models, Kelly Criterion sizing, VaR risk management, Alpaca integration
- **Honest take**: 5 stars but surprisingly well-structured. Pre-trained models included. Good risk management design. Not battle-tested though.
- **Graxia fit**: **Best reference for risk management patterns** (Kelly Criterion, VaR, stop-loss logic). Study its `src/risk/` and `src/portfolio/` structure.

---

## 🥈 Tier 2: Good References (5 repos)

### 5. t73liu/trading-bot — ⭐⭐⭐
- **What**: Go+Python trading bot with React dashboard
- **Why useful**: Full-stack (Go backend, Python ML, React UI, PostgreSQL, Terraform). Real architecture.
- **Honest take**: 23 stars but 234 commits — someone actually built this. Polyglot approach is interesting but complex.
- **Graxia fit**: Reference for full-stack trading system architecture. Study the separation of concerns.

### 6. letianzj/quanttrader — ⭐⭐⭐
- **What**: Event-driven backtest and live trading in Python
- **Why useful**: 743 stars, clean event-driven design, IB integration, supports stocks/futures/options/forex
- **Honest take**: Solid educational framework. Apache-2.0 license. Stale but well-designed.
- **Graxia fit**: Study the event-driven architecture and IB integration pattern.

### 7. cyclux/tradeforce — ⭐⭐⭐
- **What**: High-performance Python trading framework with Numba JIT
- **Why useful**: 100k+ records/sec simulation, Docker/K8s support, Optuna hyperopt, PostgreSQL/MongoDB backends
- **Honest take**: 11 stars but serious engineering. Numba acceleration is genuinely useful for backtesting speed.
- **Graxia fit**: Study for performance optimization patterns (Numba JIT, Arrow data format).

### 8. raidastauras/Trading-Bot — ⭐⭐⭐
- **What**: Research-focused FX trading bot with honest conclusions
- **Why useful**: 146 stars, honest research notes, OANDA API, multiple ML models tested
- **Honest take**: The author's honest conclusions ("predicting price direction is not really accurate") are more valuable than the code. Good reality check.
- **Graxia fit**: Study for honest research methodology and what DOESN'T work.

### 9. HKUDS/AI-Trader — ⭐⭐
- **What**: Agent-native trading platform
- **Why useful**: 20.1k stars, TypeScript+Python, agent integration API, copy trading
- **Honest take**: It's a platform/service, not a bot. Interesting concept but not directly useful for Graxia's self-hosted approach.
- **Graxia fit**: Study the agent integration pattern (SKILL.md approach) if Graxia ever needs external agent connectivity.

---

## 🥉 Tier 3: Marginal Value (7 repos)

### 10. Stefodan21/Forex-trading-bot — ⭐⭐
- PPO + AMD GPU (DirectML) + MT5. Interesting but only 12 commits, GPU support broken. Too early.

### 11. clementpl/influx-crypto-trader — ⭐⭐
- InfluxDB + Grafana monitoring. Good monitoring pattern but abandoned TypeScript project.

### 12. EthanAlgoX/LLM-TradeBot — ⭐
- 294 stars but over-engineered. 8 LLM providers, web dashboard, Docker, CLI modes... it's trying to do everything. Marketing-heavy README. The "Adversarial Decision Framework" sounds impressive but is just multi-agent debate.

### 13. StateOfTheArt-quant/sharpe — ⭐
- RL trading environment. Early alpha, incomplete. Interesting concept but not usable.

### 14. day0market/pyalgotrader — ⭐
- Fork of vnpy (Chinese framework), Google-translated. Translation quality is poor. Architecture is interesting but maintenance is questionable.

### 15. zero-was-here/tradingbot — ⭐
- 116 stars but only 6 commits. README promises 80-120% annual returns (red flag). Marketing-heavy. The "140+ features" claim is suspicious for a 6-commit repo.

### 16. The-Swarm-Corporation/BackTesterAgent — ⭐
- Thin wrapper around the Swarms framework. Only 10 commits. Not a real backtesting framework.

---

## ❌ Tier 4: Skip Entirely (10 repos)

| Repo | Reason |
|------|--------|
| Puttipong1234/BOT-TRADE-TUTORIAL | Thai tutorial repo, not production code |
| estebanthi/binance-trading-bot | Archived Oct 2025, dead |
| Hivelancee/Forex-Trading-Robot | 404 — doesn't exist |
| pkellz/everest | Abandoned 2019, Poloniex-only |
| emreeldemir/Trading-Bot | 0 stars, 3 commits, student project |
| olivierrousselle/Bot-trading-crypto | 404 — doesn't exist |
| owini/quant-research | Fork with no original work |
| mrdarylguy/trading_strategies | Script collection, not a framework |
| rom1trt/trading-bot | Personal learning project |
| FranQuant/AI-based-Trading-Strategies | 404 — doesn't exist |

---

## 🎯 Final Recommendation for Graxia

### Do NOT add any repos as direct dependencies.

### DO create a reference document with:

1. **Strategy API patterns** → from jesse-ai/jesse
2. **Risk management patterns** → from kvrancic/algorithmic-trading-bot
3. **Performance optimization** → from cyclux/tradeforce (Numba JIT)
4. **Multi-agent architecture** → from tauricresearch/tradingagents (conceptual only)
5. **Event-driven design** → from letianzj/quanttrader
6. **Honest research methodology** → from raidastauras/Trading-Bot

### What Graxia should build itself:
- Strategy interface (inspired by jesse)
- Risk management module (inspired by kvrancic)
- Backtesting engine (inspired by tradeforce's performance approach)
- Execution layer (MT5 integration, inspired by zero-was-here's structure)

### License compatibility:
- ✅ MIT: jesse, kvrancic, raidastauras, quanttrader, tradeforce
- ⚠️ GPL-3.0: freqtrade (copyleft — cannot use in proprietary code)
- ✅ Apache-2.0: tauricresearch/tradingagents

---

## 📝 Next Action

Create `Meta/references/trading_repos.md` with curated reference links and patterns to study — NOT as dependencies, but as architectural inspiration.
