# Unvalidated Paper Trading Scripts — Incident Report

**Date:** 2026-07-17
**Severity:** HIGH (operational risk, governance violation)

## Summary

Two paper trading scripts were found running with unvalidated signal logic, parallel to the research pipeline that validated and REJECT all tested strategies.

## Scripts Found Running

| Script | PID | Started | Duration | Signal Logic | Validated? |
|--------|-----|---------|----------|-------------|------------|
| `mega_paper_v4.py` | 2116 | 2026-07-16 13:58 | ~14 hours | `sig_momentum()` (line 258) | ❌ Never tested in pooled DK |
| `live_donchian.py` | 27004 | 2026-07-16 15:10 | ~13 hours | `donchian_signal()` (line 69) | ❌ Never tested in pooled DK |

## Account Details

- **Server:** Pepperstone-Demo
- **Login:** 61547941
- **Balance:** $49,841.49 USD
- **Leverage:** 200
- **Account Type:** DEMO (not live)
- **Open Positions at Stop:** None

## Why This Is a Problem

1. **Parity Gap:** Neither script imports from `strategies/*`. They have hand-rolled signal logic that was never validated through the pooled DK tests.

2. **Contradicts Validation Results:** We tested 4 Donchian variants (20/55/10/10+ADX) — all REJECT with DK t-stats as low as 0.044-0.047. The `live_donchian.py` script uses the same channel breakout concept, so it almost certainly has no edge either.

3. **Governance Violation:** Sacred holdout, stopping rule, pooled DK were all created to prevent trusting unvalidated signals. Running unvalidated code in parallel undermines the entire validation framework.

4. **Misleading Track Record:** If these scripts produce positive results by chance (short-term noise), they could be cited as "track record" despite never passing validation — similar to the BEVS pattern that looked good at 68 trades.

## Action Taken

1. ✅ Verified account type (DEMO, not live)
2. ✅ Checked for open positions (none found)
3. ✅ Documented process state (PID, start time, command line)
4. ✅ Processes stopped (PIDs 2116, 27004 no longer running)
5. ✅ Disabled scheduled tasks that would restart them:
   - `QuantOS Paper Trading` → Disabled
   - `TSM_Paper_Trading` → Disabled (launches `tsm_paper_trade.py --live`)
   - `TSM-Weekly-Rebalance` → Disabled (launches `run_tsm_weekly.ps1`)
6. ✅ Pulled trade history — 8 BTCUSD deals in last 24h, total PnL: -$1.10 (demo)
7. ✅ Incident report written

## Trade History (Last 24 Hours)

8 deals found on account 61547941, all BTCUSD:

| Ticket | Side | Price | PnL | Comment | Time |
|--------|------|-------|-----|---------|------|
| 268797230 | BUY | 64158.04 | 0.00 | F_IOC | 2026-07-16 18:07 |
| 268797299 | BUY | 64101.21 | 0.00 | TESTIOC | 2026-07-16 18:07 |
| 268797300 | SELL | 64085.78 | 0.00 | CLOSESELL | 2026-07-16 18:07 |
| 268797558 | SELL | 64093.78 | -0.64 | CLEANUP | 2026-07-16 18:09 |
| 268797559 | SELL | 64093.80 | -0.07 | CLEANUP | 2026-07-16 18:09 |
| 268797561 | BUY | 64108.82 | -0.23 | CLEANUP | 2026-07-16 18:09 |
| 268798194 | BUY | 64052.80 | 0.00 | VERIFY2 | 2026-07-16 18:10 |
| 268798202 | SELL | 64036.31 | -0.16 | VERIFY2X | 2026-07-16 18:10 |

**Total PnL: -$1.10 USD** (demo money, test/debug trades, not strategy trades)

## Root Cause Analysis

### Why did these scripts run for 13-14 hours undetected?

1. **No process monitoring:** No alerting system watches for unexpected Python processes connecting to MT5. Process lists are not checked regularly.

2. **No MT5 connection gate:** Scripts can connect to MT5 directly via `mt5.initialize()` without going through any central gateway, authentication, or approval. There is no technical mechanism to prevent unauthorized scripts from connecting.

3. **Scheduled task auto-restart:** Windows Task Scheduler had 3 tasks configured to auto-restart these scripts:
   - `QuantOS Paper Trading` → runs `run_scheduled.py`
   - `TSM_Paper_Trading` → runs `run_paper_trading.bat` → `tsm_paper_trade.py --live`
   - `TSM-Weekly-Rebalance` → runs `run_tsm_weekly.ps1`

4. **Bypass of safety infrastructure:** These scripts connect to MT5 directly, bypassing `orchestrator.py`, `OMS`, `KillSwitch`, and `PreTradeRiskGate`. Even if all safety gates were 100% functional, they would not have caught these scripts because the scripts don't use that code path.

### Structural vulnerability

The root cause is architectural: **there is no technical prevention against scripts connecting to MT5 directly.** Any Python script can call `mt5.initialize()` and start trading. The entire safety framework (KillSwitch, StateCoordinator, PreTradeRiskGate) only protects code that voluntarily uses the orchestrator/OMS path. Scripts that bypass this path are completely unguarded.

This is not a "someone forgot" problem — it's a "the system allows it" problem. No amount of process documentation prevents this; only technical controls do.

## Corrective Actions

### Immediate (done)

1. ✅ Disabled 3 scheduled tasks that would restart trading scripts
2. ✅ Verified no open positions remain
3. ✅ Documented trade history

### Short-term (should do)

4. **Add MT5 connection monitoring:** Alert when any Python process calls `mt5.initialize()` outside of approved paths
5. **Add process watchdog:** Periodic check for unexpected Python processes with `--live` or `--hours` flags
6. **Block direct MT5 access:** Consider requiring authentication through a central gateway that validates the caller

### Long-term (process)

7. **Validation gate:** No script should be allowed to connect to MT5 (even demo) without passing pooled DK validation first
8. **Code review requirement:** Any script that calls `mt5.initialize()` should be reviewed and approved before deployment
9. **Regular process audits:** Weekly check of running processes and scheduled tasks

## Recommendation

- Do NOT restart these scripts until their signal logic is validated through pooled DK tests
- Consider adding a pre-commit hook or CI check that prevents running paper trading scripts without validation
- The `tsm_paper_trade.py` script (not currently running) has the same issue and should also be blocked
- **Address the architectural vulnerability:** The lack of technical controls against direct MT5 access is the root cause. Until this is fixed, any script can bypass the safety framework.

## Related Files

- `scripts/mega_paper_v4.py` — unvalidated momentum signal
- `scripts/live_donchian.py` — unvalidated Donchian signal
- `scripts/tsm_paper_trade.py` — unvalidated TSMOM ensemble (not running)
- `scripts/run_paper_trading.bat` — launcher for tsm_paper_trade.py
- `scripts/run_tsm_weekly.ps1` — launcher for weekly TSM rebalance
- `run_scheduled.py` — scheduled task runner
- `strategies/donchian.py` — validated, REJECT
- `strategies/momentum_12m.py` — validated, REJECT
- `strategies/rsi_mean_reversion.py` — validated, REJECT/MARGINAL
