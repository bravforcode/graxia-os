# RESEARCH METHODOLOGY AUDIT — Phase 17
**Date:** 2026-07-05
**Auditor:** Strategist Agent
**Scope:** Hypothesis tracking, experiment reproducibility, version control hygiene, research debt
**Status:** READ-ONLY — no modifications made

---

## 17.1 Hypothesis Log

### Finding: RESEARCH_LOG.md is critically sparse

`RESEARCH_LOG.md:1-31` contains only 3 experiments:

| ID | Date | Status | Outcome |
|----|------|--------|---------|
| EXP-001 | 26 Jun 2026 | FAIL | "No edge after costs" — baseline test |
| EXP-002 | Pending | NOT STARTED | Session filter |
| EXP-003 | Pending | NOT STARTED | Limit order simulation |

**This is NOT a research log.** A proper hedge fund research log would contain dozens to hundreds of experiments. With only 1 completed experiment, the entire "research" claim collapses to a single failed baseline test.

### Finding: No p-values, confidence intervals, or effect sizes

EXP-001 states "Net -$1,225 vs BH +$2,888. Sharpe 0.3" — but no:
- P-value or statistical significance test
- Confidence interval on Sharpe ratio
- Effect size (Cohen's d, etc.)
- Multiple testing correction (Bonferroni, Benjamini-Hochberg)
- Sample size justification

### Finding: Meta/ directory has research artifacts but no structured log

`Meta/` contains 33 files including `research_edge_cost_report.md`, `exit_risk_research_b3.md`, `stop_loss_audit.md` — but these are standalone reports, not entries in a centralized hypothesis ledger.

### Finding: No hypothesis log format compliance

The format defined in RESEARCH_LOG.md (Hypothesis, Method, Result, Verdict) is not consistently applied. EXP-002 and EXP-003 don't even have hypotheses stated — just "pending" status.

| Severity | Finding | Evidence |
|----------|---------|----------|
| CRITICAL | Research log has only 3 entries, 1 completed | `RESEARCH_LOG.md:1-31` |
| HIGH | No p-values, CIs, or effect sizes reported | All experiment entries lack statistical rigor |
| MEDIUM | Meta/ directory contains research artifacts but no unified ledger | `Meta/` — 33 files, unstructured |

---

## 17.2 Experiment Reproducibility

### Finding: Random seeds are consistently fixed

68 occurrences of `random_state=42`, `RANDOM_STATE=42`, or `np.random.seed(42)` across scripts. This provides INPUT reproducibility within the same library versions.

### Finding: No full-pipeline reproducibility verification

`scripts/verify_reproducibility.py:1-23` only hashes CSV data files:
```python
for csv in sorted(csvs):
    h = hashlib.sha256(csv.read_bytes()).hexdigest()
```
This verifies INPUT hash, NOT output reproducibility. There is no script that:
1. Loads the same data/config
2. Runs the full pipeline (features → train → backtest)
3. Compares results byte-for-byte or metric-for-metric against a known baseline

### Finding: Intermediate files are regenerable but not committed

`.gitignore` excludes `*.pkl`, `*.parquet`, `*.csv`, `*.duckdb` — these are regenerable from source data. However, source data files themselves are ALSO excluded (`data/*.csv`). This means:
- Training data (CSVs) are NOT in version control
- If data is lost, re-download from external source required
- No guarantee that re-downloaded data matches original training data

### Finding: Parquet feature files exist at `artifacts/features_v3/`

`train_live_model.py:40`: `FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"` — these are generated from `scripts/build_features.py` / `scripts/build_mega_features.py`. Regenerable but time-consuming.

### Finding: LockedInputs framework exists but covers strategy, not data

`validation/locked_inputs.py:7-61` provides immutable `LockedInputs` with:
- strategy_source_hash, strategy_param_hash
- dataset_manifest_hash, timeframe_alignment_hash
- execution_model_version, contract_snapshot_version
- risk_policy_version, event_filter_version
- random_seed

This is designed for validation reproducibility but only locks STRATEGY inputs — not the data snapshot or model version.

| Severity | Finding | Evidence |
|----------|---------|----------|
| HIGH | No full-pipeline reproducibility test exists | `verify_reproducibility.py:1-23` — CSV hash only |
| MEDIUM | Training data (CSVs) excluded from git — cannot reproduce from repo alone | `.gitignore:22-24` excludes `data/*.csv` |
| MEDIUM | LockedInputs covers strategy but not model version or data snapshot | `validation/locked_inputs.py:7-15` — no model_hash field |

---

## 17.3 Version Control Hygiene

### Finding: Git commits use conventional commits — GOOD

`git log --oneline -30`:
```
86c0e61e chore(quant_os): untrack CSV+chroma data, commit remaining source mods
2cde5c68 feat(quant_os): dashboard VPS deploy + multi-symbol Linux + 24 new tests (75/75)
f416d117 feat(quant_os): data pipeline scripts + OOS tests + M1 paper trading
cd7fef5d chore(quant_os): backtest engine, ensemble, swap cost, scripts, known limitations
74b23135 fix(quant_os): weekend guard, first-cycle init, heartbeat always-on, gitignore chroma+CSV, smoke test
... (all use conventional commit format with quant_os scope)
```
Commit messages are meaningful and well-structured.

### Finding: .gitignore properly excludes sensitive files — GOOD

`.gitignore:1-32` excludes: `__pycache__/`, `*.pkl`, `*.parquet`, `*.csv`, `*.duckdb`, `.env`, `data/warehouse/`, `data/ticks/`, `credentials files`. **However, the old `Meta/pepperstone_creds.txt` file was removed and replaced with `.backup` per v4 AUDIT_INDEX.md.**

### Finding: One .ipynb file exists (dashboard.ipynb) — not critical

`dashboard.ipynb` is excluded from git (`.gitignore:24`). It appears to be a visualization dashboard, not critical trading logic. Only one notebook found — no systemic notebook dependency issue.

### Finding: No committed output notebooks with uncleared cells

Only 1 notebook, and it's gitignored. Clean.

| Severity | Finding | Evidence |
|----------|---------|----------|
| PASS | Conventional commit messages throughout | `git log --oneline -30` — all scoped |
| PASS | .gitignore properly configured | `.gitignore:1-32` — excludes credentials, data, artifacts |
| PASS | No critical logic in notebooks | Only `dashboard.ipynb`, gitignored |

---

## 17.4 Research Debt

### Finding: No TODO/FIXME/HACK in production code

Grep for `TODO|FIXME|HACK|WORKAROUND` across all `.py` files found matches ONLY in `scripts/audit_full.py` (the audit scanner itself, looking for these markers). **Zero TODO/FIXME/HACK in production code.** This is either excellent discipline or incomplete documentation of known issues.

### Finding: 8 `raise NotImplementedError` in stub modules

| File | Line | Context |
|------|------|---------|
| `alpha/engine.py:486` | Crypto strategies not yet implemented |
| `alpha/engine.py:491` | Forex strategies not yet implemented |
| `alpha/engine.py:496` | Indices strategies not yet implemented |
| `repo_intelligence/adapters/lean_oracle_contract.py:16` | LEAN validate_input stub |
| `repo_intelligence/adapters/lean_oracle_contract.py:25` | LEAN normalize_output stub |
| `repo_intelligence/adapters/lean_oracle_contract.py:39` | LEAN get_lean_config_brokerages stub |
| `repo_intelligence/adapters/lean_oracle_contract.py:47` | LEAN get_lean_data_feed_types stub |

The `alpha/engine.py` stubs are placeholders for multi-asset expansion. The Lean oracle stubs are for a planned LEAN integration. **These are expansion features, not broken production code.**

### Finding: 1 quarantined test

`quarantine_manifest.json` shows 1 quarantined test (`test_vwap.py`) for data format mismatch — non-blocking, with verified coverage by `test_timing.py`.

### Finding: 13 bare `except:` clauses

| File | Lines |
|------|-------|
| `check_quality.py` | 51, 68 |
| `scripts/diagnose_leakage.py` | 91 |
| `scripts/health_check.py` | 78 |
| `scripts/research_final.py` | 244 |
| `scripts/research_carry_news.py` | 30, 158, 160 |
| `scripts/research_comprehensive.py` | 36, 245 |
| `scripts/run_complete_analysis.py` | 31, 141 |
| `scripts/run_lagged_wf.py` | 58 |

All are in `scripts/` or root-level quality check files — NOT in `core/`, `risk/`, `execution/`, `backtest/`, or `ml/`. Production modules properly handle exceptions.

### Finding: Core production modules do NOT use bare except

`core/event_bus.py:134` uses `except Exception as e:` (proper). `core/trading_loop.py:358` uses `except Exception as exc:` (proper). Production paths handle exceptions correctly.

| Severity | Finding | Evidence |
|----------|---------|----------|
| LOW | 8 NotImplementedError in stub/expansion modules | `alpha/engine.py`, `lean_oracle_contract.py` |
| LOW | 13 bare except clauses in non-critical scripts | All in `scripts/` or root quality check files |
| INFO | 1 quarantined test, non-blocking | `quarantine_manifest.json` |

---

## 17.5 Notebook vs Script Discipline

### Finding: Clean — no notebook dependency

- Only 1 `.ipynb` file (`dashboard.ipynb`) — gitignored, not critical
- All strategy, execution, and ML logic is in `.py` scripts/modules
- No evidence of "run cells 1-3, then 7, then 4" notebook workflows

| Severity | Finding | Evidence |
|----------|---------|----------|
| PASS | All critical logic in importable Python modules | No notebook dependency found |

---

## 17.6 Audit-of-Audits / Finding Persistence Tracking

### Finding: Multi-level audit tracking exists

| Audit Document | Date | Scope |
|---------------|------|-------|
| `reports/AUDIT_INDEX.md` | 2026-06-29 | v3 Protocol — 28 phases, 8 P0 blockers |
| `reports/deep_audit_v4/AUDIT_INDEX.md` | 2026-07-05 | v4 Protocol — 28 phases, 4 P0 blockers (updated) |
| `reports/FULL_REPOSITORY_AUDIT.md` | 2026-06-25 | Complete pre-audit census |
| `reports/CORRECTIVE_AUDIT_ADDENDUM.md` | 2026-06-25 | 3 critical gap analysis |
| `reports/deep_audit_v4/` | 2026-07-05 | 27 v4 phase reports |

### Finding: 4 P0 fixes claimed, partially verified

From `deep_audit_v4/AUDIT_INDEX.md:103-141`:
1. **KNOWN_LIMITATIONS.md clarification** — Fixed (documentation)
2. **Ensemble SL/TP consensus** — Fixed (code change in `strategies/ensemble.py:422-460`)
3. **Walk-forward cost calculation** — Fixed (code change in `scripts/walk_forward.py:49-143`)
4. **Credentials file removed** — Fixed (`Meta/pepperstone_creds.txt` → `.backup`)

### Finding: Prior v3 P0 blockers NOT fully resolved

From `reports/AUDIT_INDEX.md:23-30` (v3, June 29):
1. **BUG-SL/TP**: SL/TP trigger uses bar midpoint — `execution/fill_model.py:67-87`
2. **BUG-SWAP**: Swap costs never applied — `backtest/engine.py:125`
3. **BUG-KILL**: Kill switch resets to OFF on corrupt JSON — `risk/kill_switch.py:149-151`
4. **BUG-PRETRADE**: Pre-trade gate not wired — `execution/manager.py:115-116`
5. **BUG-RECOVERY**: Crash recovery dead code — `execution/recovery.py`
6. **SEC-KEYS**: 3 API keys hardcoded — `data_pipeline/config.py:20-22`
7. **SEC-MT5**: MT5 account in git history — `scripts/export_mt5_historical.py:14`
8. **SEC-ENV**: Real FRED key in .env.example — `config/.env.example:1`

**v4 AUDIT_INDEX.md does NOT mention fixing items 1-5 from this list.** The 4 P0s fixed in v4 are DIFFERENT from the 8 P0s identified in v3. The v3 P0s have not been dispositioned.

### Finding: Contradiction between v3 and v4 statuses

| Finding | v3 Status (Jun 29) | v4 Status (Jul 05) |
|---------|-------------------|-------------------|
| SL/TP midpoint bug | P0 — fix needed | Not in v4 P0 list |
| Missing swap costs | P0 — fix needed | Claimed "fixed" per `engine.py:220-245` |
| Kill switch crash safety | P0 — fix needed | Not in v4 P0 list |
| Pre-trade gate unwired | P0 — fix needed | Not in v4 P0 list |
| Crash recovery dead code | P0 — fix needed | Not in v4 P0 list |

**5 of 8 v3 P0s are unaccounted for in v4.** The swap cost fix is claimed in v4 but the other 4 are neither confirmed fixed nor carried forward as open issues.

| Severity | Finding | Evidence |
|----------|---------|----------|
| CRITICAL | 5 of 8 v3 P0 blockers not dispositioned in v4 | Compare `reports/AUDIT_INDEX.md:23-30` vs `reports/deep_audit_v4/AUDIT_INDEX.md:35-43` |
| HIGH | No recurrence tracking — v3 findings not traced to v4 status | Gap between v3 8 P0s and v4 4 P0s |
| INFO | Audit tracking infrastructure exists (INDEX + phase reports) | Structured, findable |

---

## Summary: Phase 17 — Research Methodology

| Area | Status | Top Issue |
|------|--------|-----------|
| Hypothesis Log | FAIL | Only 3 entries, 1 completed — not a research log |
| Experiment Reproducibility | PARTIAL | Seeds fixed but no full-pipeline repro test |
| Version Control | PASS | Conventional commits, good .gitignore |
| Research Debt | PASS | No TODO/FIXME in production; bare excepts only in scripts |
| Notebook Discipline | PASS | Zero dependency on notebooks |
| Audit Persistence | PARTIAL | Multi-level tracking exists but 5 v3 P0s unaccounted for in v4 |

### Top 3 P0 Findings:
1. **RESEARCH_LOG.md is critically sparse** — 3 entries, 1 completed, no p-values, no CIs, no effect sizes (`RESEARCH_LOG.md:1-31`)
2. **5 of 8 v3 P0 blockers not dispositioned in v4** — finding persistence broken between audit versions
3. **No full-pipeline reproducibility verification** — only CSV hash checks, no output comparison test
