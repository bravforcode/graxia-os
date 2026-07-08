# Live Trading Checklist — Manual Steps Required

> Generated 2026-07-07 from deep security audit

## Before Live Trading (MUST complete all):

### Secrets Rotation (manual — cannot automate)
- [ ] Change MT5 password in MetaTrader 5 terminal
- [ ] Revoke old Telegram bot token via @BotFather, create new bot
- [ ] Change PostgreSQL password
- [ ] Revoke old LLM API keys (Groq, Google AI, Cerebras, OpenRouter, Cohere) in each provider console
- [ ] Update .env with all new values
- [ ] Restart all services

### Paper Trading Campaign (Golden Rule #3)
- [ ] Run paper trading for minimum 60 days
- [ ] Execute minimum 100 paper trades
- [ ] Verify win rate and profit factor meet thresholds
- [ ] Document results in reports/paper_campaign_*

### Validation (Golden Rule #4-6)
- [ ] Walk-forward validation: minimum 3 windows
- [ ] PBO (Probability of Backtest Overfitting) < 0.5
- [ ] Deflated Sharpe Ratio > 0
- [ ] Multiple testing correction applied
- [ ] Backtest span: minimum 3 years

### Smoke Test (24-hour dry run)
- [ ] Run 24-hour dry run with full order lifecycle
- [ ] Verify kill switch activates and closes positions
- [ ] Verify reconciliation loop detects discrepancies
- [ ] Verify Telegram alerts fire correctly
- [ ] Verify Prometheus metrics export

### Human Approval (CHANGE_CONTROL.md)
- [ ] Human reviewer signs off on CHANGE_CONTROL.md
- [ ] Evidence pack assembled with all test results
- [ ] No live action without separate explicit approval

## Automated Checks (enforced by ProductionReadiness gate):
- API keys configured
- Risk limits set
- Canonical payloads in use
- Hot path latency < 10ms
- No raw dicts in EventBus
- Kelly sizing active
- Correlation filter active
- Session filter active
- News blackout active
- Walk-forward models available
- Overfitting detector available
