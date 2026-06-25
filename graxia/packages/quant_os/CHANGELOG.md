# Changelog

## 0.2.0-dev (2026-06-25)

### Features
- regime filter + confidence threshold — first positive expectancy
- regime accuracy diagnostic -- find accuracy clusters by regime
- V2 pipeline -- order-flow features, triple-barrier labels
- ML pipeline — feature engineering + strategy model
- complete all — scheduler, phase tests, parquet, G4.1, telegram, multi-broker, ML model
- 12 upgrades — scheduler, heatmap, dashboard, ML model, research, parquet plan
- mega data collector — bulk ticks + batch orders + dataset builder
- BE-P8.5 — Pepperstone 24h campaign runner (1186/1186 pass)
- BE-P8.4 — canonical tick authority migration (1167/1167 pass)
- BE-P8.3.3 — Pepperstone broker profile + 4-variant diagnostic matrix
- BE-P8.3.2 — time source reconciliation (3-source cross-check, 4 guards, 1140/1140 pass)
- BE-P8.3.1 — clock provenance investigation (3-source cross-check, raw evidence)
- BE-P8.2 — first real MT5 shadow run (5 cycles, 2 accepted, 3 stale-rejected)
- BE-P8.2 — broker-observed shadow runner (read-only MT5, full metadata, sealed ledger)
- BE-P8.1 — shadow integrity repair (geometry gate, spread shock, dedup, lifecycle)
- BE-P13 — controlled expansion (planner, tracker, forbidden guard, readiness check)
- BE-P12 — guarded micro-live (policy, preflight, risk check, evidence pack, review verdict)
- BE-P11 — promotion review (decision engine, evidence pack, auto-blockers, review report)
- BE-P10 — demo campaign + drills (13 drill types, daily/weekly reports, scorecard)
- BE-P9 — MT5 demo canary (config, 15-state lifecycle, preflight, order guard, runner)
- BE-P8 — shadow campaign (pipeline, telemetry, pass criteria, campaign manager)
- BE-P7 — EURUSD clean research foundation (hypothesis, anti-contamination, session/event calendar)
- BE-P6 — locked revalidation (run matrix, decision gates, revalidation runner, threshold evaluator)
- BE-P5 — oracle validation (strategy IR, differential comparator, adapter base, environment isolation)
- BE-P4 — empirical cost calibration (labeled costs, quote calibration, stress analyzer)
- implement 6 skipped items (stale/session_break, parquet/DuckDB, UNKNOWN_FAIL_CLOSED)
- BE-P3 — event-risk + market-health gates (state machine, provider, isolation)
- BE-P2 — tick capture (schema, storage, quality, recorder, feed health, metrics)
- BE-P0 fixes (fingerprint timestamps, from_mt5 skip, max_depth scan) + BE-P1
- BE-P0 — credential remediation, broker identity guard, secret provider, redaction
- Phase 11 — controlled expansion (4-tier policy, multi-broker policy)
- Phase 10 — micro-live canary (policy, emergency kill switch)
- Phase 9 — controlled micro-live review (checklist, outcomes, report template)
- Phase 8 — demo campaign drills (10 drill types, executor, scorecard)
- Phase 7 — MT5 demo readiness (canary config, demo policy, protective stop)
- Phase 6 — shadow mode (pipeline, telemetry, market health, event risk, MT5 connector)
- Phase 5 — statistical validation (experiment registry, WFO, deflated Sharpe, PBO)
- Phase 4 — EURUSD clean research foundation (manifests, contract, anti-contamination)
- Phase 3B — frozen XAUUSD fixture, R0-R3 cost scenarios, oracle comparison
- Phase 1R-H — oracle adapters (VBT/BT/BTR), differential comparator, isolation
- Phase 3.1A.2 — 562/562 pass, quarantine manifest, fail-closed release gate, determinism
- Phase 3.1A.1 — full suite repair, E2E semantics, engine ledger tamper, release gate
- Phase 3.1A — engine evidence, ledger integrity, provenance, E2E fixture, import isolation
- Phase 3.1 — canonical engine integration (sizing, fill, cost, state machine, ledger)
- G0.1 closeout — provenance fix, AST regression guard, hftbacktest quarantine, freeze
- G0 — freeze + canonical runtime map + legacy audit + governance docs
- Phase 1R — repository intelligence + registry + adapters + firewall tests
- Phase 3 — bid/ask execution + cost model + order lifecycle
- Phase 2 — contract-aware sizing + pre-trade risk engine
- MT5 real data + supply_demand min SL + adapter multi-TF support

### Fixes
- Bonferroni + walk-forward diagnostic — corrected signal analysis
- fill simulator + feature diagnostic — 3 critical ML fixes
- auto-reconnect + checkpoint bug (variable shadowing) + graceful exit
- lint — remove unused tqdm import, 10 f-string/import fixes from ruff
- BE-P8.5 — add MT5 connect() call before campaign loop
- BE-P8.3 prep — UTC timestamps, tick diagnostics, runtime firewall
- BE-P8.1 — shadow integrity repair (geometry gate, spread shock, dedup, lifecycle)
- MTF cursor prevents look-ahead leakage
- ATR-adaptive SL/TP for cross-symbol compatibility
- baseline bugfixes - vwap division by zero, supply_demand zone_range guard

### Optimizations
- mega_collect P1-P4 — spread gate, resume, tick context, phase tests
- mega_collect — add deviation, limit mode, schedule params
- research-based tuning for 5 losing strategies + SL bug fixes
- tune 7 strategies - liquidity_sweep 2.5x R:R, supply_demand fixed SL 18pt

### Security
- remove credentials, add secret scanner, gitignore configs

### Documentation
- G0.1 closeout verdict — PASS_TO_PHASE_3_1, 6/6 tests PASS
- Phase 3 report — PASS_TO_PHASE_1R
- Phase 2 report — PASS_TO_PHASE_3
