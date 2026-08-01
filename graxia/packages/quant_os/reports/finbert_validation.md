# FinBERT Validation Report

## Summary

| Metric | Value |
|--------|-------|
| Headlines tested | 100 |
| FinBERT vs Ollama agreement | 58.0% |
| Processing time | 3.5s (0.04s/headline) |
| Model | ProsusAI/finbert |

## Sentiment Distribution

| Sentiment | FinBERT | Ollama |
|-----------|---------|--------|
| positive | 26 | 32 |
| negative | 22 | 33 |
| neutral | 52 | 35 |

## Agreement by Sentiment

- Ollama=positive: 17/32 agree (53%)
- Ollama=negative: 16/33 agree (48%)
- Ollama=neutral: 25/35 agree (71%)

## Disagreements (42 total)

| Ollama | FinBERT | Title |
|--------|---------|-------|
| negative | neutral | Nikkei: US Treasury Department tells traders, prepare for po |
| positive | neutral | Quantum computing nears commercial breakthrough, IBM CEO say |
| positive | neutral | XDC AI and the Rise of Agentic Finance: When AI Agents Learn |
| neutral | positive | Bowen: Plan for Hamas to disarm faces big obstacles, yet it  |
| negative | neutral | Suspects confess to murder: what is known about disappearanc |
| negative | neutral | Coldcard Wallet Flaw Exposes Years of Bitcoin Seeds After $7 |
| positive | neutral | This rare and bullish signal just triggered for the Nasdaq – |
| neutral | positive | Russia wins silver in Diving Mixed Team at 2026 European Aqu |
| positive | neutral | TD Cowen raises Rivian stock price target on Q2 results, R2  |
| positive | neutral | Moonshot has Nvidia chip cluster from Alibaba computing deal |
| positive | neutral | Uniswap launches ‘Earn’ with Morpho to let users earn yield  |
| negative | neutral | Russia deploys Black Kite drones to special military operati |
| negative | neutral | COLDCARD SECURITY RISK: IMMEDIATE ACTION REQUIRED |
| neutral | positive | Bank of Canada: Strong GDP lowers cut risk – TD Securities |
| neutral | negative | USDCAD buyers reverse the declines from yesterday. MA resist |
| negative | neutral | Europe braces for wave of wildfires as prospects rise for ‘o |
| negative | neutral | Crypto faces 3 barriers to next bull run, STS Digital CEO sa |
| negative | neutral | How Leopold Aschenbrenner built a $45 billion AI hedge fund  |
| positive | neutral | Ares Management Corporation declares $1.35 dividend |
| negative | neutral | Ghosts of the 1970s: Why three Fed hawks voted to spike rate |

## Conclusion

FinBERT agrees with Ollama qwen3.5:9b only 58.0% of the time. Low agreement. Ensemble may not be beneficial. Investigate further.