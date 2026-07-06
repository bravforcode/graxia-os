# PHASE 23 — OPERATIONAL CONTINUITY AUDIT
**Date:** 2026-07-06 | **Auditor:** Final Synthesis Agent | **Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v4.md
**Scope:** Runbook completeness, tribal knowledge dependency, single points of failure, RTO/RPO, incident response capability

---

## 23.1 Runbook Integrity

### Question: Is there a single document from which someone can safely start, stop, and monitor this system?

**Answer: PARTIAL — RUNBOOK.md exists but is insufficient for safe operation.**

`reports/RUNBOOK.md` covers:
- Start commands (paper trading, shadow mode) ✅
- Emergency stop (Ctrl+C, Telegram /kill_all, manual MT5 close) ✅
- System status (dashboard, health endpoint, log locations) ✅
- Kill switch commands (partial — Telegram commands listed) ✅
- Crash recovery (Recovery.on_startup() described) ✅
- Log file locations ✅
- Alert channel list ✅
- Incident runbooks (brief scenarios) ⚠️ PARTIAL

**What RUNBOOK.md is MISSING:**

| Missing Item | Severity | Why It Matters |
|-------------|----------|----------------|
| **How to verify paper vs. live mode BEFORE starting** | **P0** | KNOWN_LIMITATIONS.md P0 finding — operator must know which adapter path is active |
| **Pre-start checklist** (MT5 terminal running? credentials accessible? broker connection confirmed?) | **P0** | Starting without MT5 terminal = silent failure |
| **How to confirm the system is actually placing/monitoring orders** | **P1** | First 5 minutes of operation — dead bot looks identical to dormant bot in logs |
| **What to do if the bot crashes with a position open** | **P0** | RUNBOOK.md describes Recovery.on_startup() but not: manual position closure procedure, broker portal login steps, margin level verification |
| **How to detect and respond to a split-brain scenario** (two bot instances running against same MT5 account) | **P0** | No mention of pidfile, instance lock, or duplicate detection |
| **How to rotate credentials** | **P2** | Pepperstone password change procedure not documented |
| **Dependency update protocol** | **P2** | No instructions for safe pip/conda update |
| **Log rotation and retention schedule** | **P2** | Logs rotate at 10MB but no cleanup policy documented |
| **How to verify that data feed is live and accurate** | **P1** | No data quality check procedure |
| **Weekend/maintenance shutdown procedure** | **P1** | No instructions for end-of-week behavior |
| **Expected resource consumption** (CPU, RAM, disk) | **P2** | No baseline resource profile |

---

## 23.2 Tribal Knowledge Assessment

### Question: What knowledge exists ONLY in the developer's head?

**Answer: SIGNIFICANT tribal knowledge risk.**

| Knowledge | Documentation Status | Risk if Developer Unavailable |
|-----------|---------------------|-------------------------------|
| Which strategy weights are current | Hardcoded in `ensemble.py:469-473` but no rationale documented | Low — code is source of truth |
| Why ensemble thresholds (0.60, 0.40) were chosen | Not documented anywhere | High — retuning requires understanding design intent |
| Which broker adapter is canonical (mt5.py vs. broker_adapter.py vs. mt5_gateway.py) | Now clarified in KNOWN_LIMITATIONS.md | Medium — improved but still confusing |
| How to interpret walk_forward.py output | Not documented | High — requires understanding of signal/label conventions |
| What to do when auto_retrain triggers | Not documented | High — model artifacts must be manually deployed |
| Which of 3 heartbeat systems runs in production | Not documented anywhere | Critical — health_check.py, dead_mans_switch.py, and heartbeat_monitor.py have different timeouts |
| How to add a new trading instrument | Not documented | Medium — involves contract specs, feature generation, model training, ensemble config |

**The developer cannot get hit by a bus and expect someone else to operate this system within a day.** Even with RUNBOOK.md and the audit reports, critical operational decisions require knowledge the audit agent itself had to trace through source code.

---

## 23.3 Single Points of Failure (SPOF)

| SPOF | Description | Impact if Fails | Mitigation? |
|------|-------------|-----------------|-------------|
| **MT5 terminal connection** | Single `mt5.initialize()` call in MT5Adapter | All trading stops, positions unmonitored | ⚠️ `_ensure_connected()` retry loop exists, but no failover broker |
| **One VPS / one machine** | Entire system runs on single host | VPS crash with positions open = blind | ❌ No standby VPS configured (health_check.py has STANDBY_WEBHOOK_URL but not proven operational) |
| **Single DuckDB/RocksDB instance** | Trade state, positions, ledger in local DB | DB corruption = losing all position state | ❌ No replication, no backup procedure documented |
| **Single MT5 broker account** | All positions are with Pepperstone | Broker outage = cannot manage positions | ❌ No secondary broker configured |
| **Single data source** (MT5) | Market data comes from MT5 only | MT5 data feed stale = feature computation broken | ❌ No secondary data feed |
| **Single Telegram bot** | All alerts go through one bot | Telegram banned/blocked = no alerts | ⚠️ Prometheus/Grafana configured but integration unclear |
| **Single .env credential store** | All secrets in one environment file | .env lost = cannot start, cannot reconnect | ❌ No password manager backup |
| **No pidfile/instance lock** | Nothing prevents two bot instances from running | Two bots on same MT5 account = duplicate orders, double risk | ❌ No instance exclusivity enforcement |

---

## 23.4 Recovery Time Objective (RTO)

### Scenario: VPS dies with 1 open position

**What happens:**
1. Position is open on MT5 broker server (broker holds the position)
2. Bot goes silent — no monitoring, no SL management
3. MT5 server-side stop-loss (if placed) still active — partial protection if SL was submitted
4. Take-profit (if placed) still active on server
5. Position will close at SL, TP, margin call, or manual intervention

**Time to recover:**
| Step | Estimated Time | Notes |
|------|---------------|-------|
| Detect bot is dead | 5-30 minutes | Depends on heartbeat monitoring setup (3 overlapping systems — unclear which is active) |
| Access VPS/broker portal | 2-10 minutes | Depends on developer's availability |
| Verify position status in MT5 portal | 1-2 minutes | Requires Pepperstone portal credentials |
| Decide: close manually or resume bot | 2-30 minutes | Depends on assessment of missed market movement |
| Resume bot with Recovery.on_startup() | 2-5 minutes | Reconciliation should detect orphan position |
| Verify reconciliation correct | 5-15 minutes | Manual review required for side/qty mismatches |

**Estimated RTO: 15-90 minutes** — depending on developer availability and detection latency. During this window, an open position has no active SL/TP management if bot-placed SL/TP wasn't submitted as server-side order.

**RPO (Recovery Point Objective):**
- DuckDB state = last known before crash (no replication)
- MT5 server = authoritative for positions (broker holds ground truth)
- Reconciliation on restart should align internals with broker

---

## 23.5 Key Phase 23 Findings

| # | Severity | Finding |
|---|----------|---------|
| 1 | **P0** | No pre-start checklist to verify paper vs. live mode, MT5 terminal status, or broker connection |
| 2 | **P0** | No procedure for "crash with open position" — RUNBOOK describes automated recovery but not manual fallback |
| 3 | **P0** | Significant tribal knowledge — operational decisions span hundreds of lines of undiscoverable reasoning |
| 4 | **P1** | 8+ single points of failure, no documented failover for any of them |
| 5 | **P1** | Three overlapping heartbeat systems — unclear which runs in production |
| 6 | **P1** | No instance lock / pidfile — two bots on same account would submit duplicate orders |
| 7 | **P2** | RUNBOOK.md missing pre-start checklist, credential rotation, dependency update, and resource profile |

---

## 23.6 Verdict

**FAIL** — A third party with RUNBOOK.md and full source code access would need 1-2 days of code tracing to safely operate this system. Tribal knowledge is high, SPOFs are unmitigated, and the crash-with-open-position scenario has no documented manual recovery path. The system is not operationally mature enough for unattended live trading.
