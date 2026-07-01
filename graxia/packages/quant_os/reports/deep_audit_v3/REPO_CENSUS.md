# PHASE 0 — REPOSITORY CENSUS
*Audit date: 2026-06-29 · Branch: staging · Per R1–R18*

> Method: directory tree via `mcp__lean-ctx__ctx_tree`, file/LOC counts via Python walk, dependency inventory from `requirements.txt`, data files via `data/` listing. Every claim below is verified against files on disk or marked `[UNVERIFIED]`.

---

## 0.1 — File & Directory Tree (top-level)

Repo root: `graxia/packages/quant_os/` — **813 Python files, ~136,961 LOC** (excluding `.venv`, `__pycache__`, caches, `graphify-out`).

Module layout (concern-grouped, per AGENTS.md):
- **Domain logic**: `core/` (77 entries), `execution/` (25), `risk/` (16), `validation/` (36), `strategies/` (7), `regime/` (13), `alpha/` (3), `analysis/` (2), `oracle/` (11), `cost/` (11)
- **Runtime/integration**: `api/` (11), `broker/` (4), `live_readiness/` (8), `market_data/` (12), `shadow/` (42), `canary/` (32), `micro_live/` (12), `monitoring/` (15), `events/` (14), `news_events/` (7), `mt5_connector/` (6), `tick/` (9), `ticks/` (9)
- **Research/backtest**: `backtest/` (16), `expansion/` (12), `experiments/` (10), `data_pipeline/` (29)
- **ML**: `ml/` (8), `fin_model/` (1 — a `.tar.gz` archive)
- **Parallel/legacy system**: `gold_bot/` (36 — appears to be a second, separate bot implementation)
- **Meta/state**: `Meta/` (98 entries — docs, states, research, `pepperstone_creds.txt`, `tasks/`), `state/` (2)
- **Reports**: `reports/` (58 prior audit/report files), `results/` (4 backtest JSON)
- **Data**: `data/` (275 entries — CSV per symbol/timeframe, `.duckdb`, `fred/`, `news/`, `market_data/`)
- **Scripts**: `scripts/` (143 one-off/research scripts), `_scripts/` (2)

**Files ≥ 500 lines requiring decomposition review** — 53 total. Top offenders (consequence-ranked):
| LOC | File | Risk |
|---|---|---|
| 1305 | `tests/chaos/run_chaos.py` | low (test) |
| 1090 | `backtest/engine.py` | **HIGH** — core trading engine, single class |
| 951 | `gold_bot/core/engine.py` | **HIGH** — second engine, parallel to main |
| 1025 | `scripts/build_features.py` | med — feature engineering, leakage surface |
| 767 | `shadow/broker_observed_runner.py` | med |
| 28.8KB | `run_paper_trading.py` (live entry) | **HIGH** — live entry point |

**Generated/compiled vs hand-written**:
- `catboost_info/` (training artifacts), `lancedb/__manifest/`, `graphify-out/manifest.json`, `fin_model/fin_model.tar.gz`, `data/*.duckdb` — all generated.
- `ml/models/` (model artifact), `.mypy_cache`, `.ruff_cache`, `.pytest_cache` — generated.
- Everything else appears hand-written source.

---

## 0.2 — Dependency Inventory

Pinned in `requirements.txt` (auto-generated 2026-06-27, "Python 3.11+ / Windows x64"). Selected risk-relevant:

| Library | Version | Class | Risk note |
|---|---|---|---|
| `MetaTrader5` | `==5.0.5735` | broker | **Must match broker terminal build — UNVERIFIED terminal build on host (no `mt5 terminal_info` output captured).** R6.2 item. |
| `ccxt` | `>=4.0.0` | broker | **unpinned** — drift risk (R19.3) |
| `pandas` | `==2.3.3` | data | pinned ✓ |
| `numpy` | `>=1.26.4,<2.1` | data | range — OK |
| `vectorbt` | `==1.0.0` | backtest | pinned, but see Phase 7 oracle test note |
| `nautilus_trader` | `==1.221.0` | backtest | pinned |
| `scikit-learn` | `==1.9.0` | ML | pinned |
| `xgboost` | `==3.2.0` | ML | pinned |
| `python-telegram-bot` | `>=20.0` | notify | **unpinned** |
| `structlog` / `prometheus-client` | `>=…` | observability | **unpinned** |
| `pydantic` / `pydantic-settings` | `>=2.0.0` | config | **unpinned** |
| `pandas_ta` | *(not in requirements)* | indicator | **CRITICAL: `backtest/engine.py:621-667` imports `pandas_ta` but it is NOT in `requirements.txt`.** Either it is installed transitively or the pandas path silently fails via bare `except ImportError` at `engine.py:669` → indicators silently empty → strategy gets no indicators. [VERIFIED import + bare except] |

**Supply-chain / vuln scan**: `[NO SCAN RUN]` — no `pip-audit` output or evidence anywhere in repo. `MetaTrader5` confirmed importable path is `import MetaTrader5 as mt5` (`mt5_connector/connection.py:57`). Cannot verify it was installed from official PyPI vs. a wheel file without `pip show` access — `[UNVERIFIED]`.

---

## 0.3 — Entry Points

| Mode | Command | `file:line` |
|---|---|---|
| Backtest (research, canonical engine) | `python run_backtest.py` | `run_backtest.py:207` (`if __name__ == "__main__": main()`) — downloads Yahoo data, runs MTM/MRB/MLB via `BacktestEngine` |
| Backtest (the one producing `results/*.json`) | `python scripts/backtest_suite.py` | `scripts/backtest_suite.py` — **DIFFERENT code path, no `BacktestEngine`, no cost model** (see Phase 7) |
| Paper trading | `python run_paper_trading.py` | `run_paper_trading.py:1` (`PaperTrader`) — MT5 live feed + `PaperBroker` |
| Paper (PowerShell) | `./run_paper_trading.ps1` | |
| ML training | `python run_ml_train.py` / `run_ml_train.py` | |
| Shadow mode | `python run_shadow.py` | |
| API surface | `python api/main.py` | FastAPI (`api/main.py`) |

**`if __name__ == "__main__"` guard consistency**: present in `run_backtest.py:207`, `run_paper_trading.py` (asyncio.run pattern), `ml/labeling.py:241`. Not exhaustively audited across 813 files.

**Mode flag plumbing**: `core/config.py:128` reads `TRADING_MODE` env; `core/config.py:176-198` `_validate_mode_consistency()` enforces PAPER/LIVE consistency and requires secrets when live. **But the actual paper-trading entry (`run_paper_trading.py`) constructs `PaperBroker()` directly (`run_paper_trading.py:43`) and does NOT go through the canonical `BacktestEngine`** — this is a Phase 8 parity concern.

---

## 0.4 — Configuration Inventory

Two config systems coexist:

**A. `core/config.py:QuantConfig`** (env-driven dataclass)
| Parameter | Default | `file:line` | Used in |
|---|---|---|---|
| `mt5_server` | `ICMarketsSC-Demo` | `core/config.py:32` | live path |
| `symbols` | EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,XAUUSD | `core/config.py:52-54` | everywhere |
| `primary_timeframe` | `M15` | `core/config.py:57` | |
| `max_risk_per_trade_pct` | 1.0 | `core/config.py:61` | soft limit |
| `max_daily_loss_pct` | 2.0 | `core/config.py:62` | soft limit |
| `max_drawdown_pct` | 10.0 | `core/config.py:64` | soft limit |
| `max_positions` | 5 | `core/config.py:66` | |
| `units_per_lot` | 100000.0 | `core/config.py:87` | |
| `paper_slippage_pips` | 0.5 | `core/config.py:91` | |
| `paper_commission_per_lot` | 3.5 | `core/config.py:92` | |

**B. `risk/risk_policy.py:RiskPolicy`** (frozen, bps-based)
| Parameter | bps | `file:line` | Meaning |
|---|---|---|---|
| `risk_per_trade_bps` | 10 | `risk_policy.py:10` | 0.10% |
| `max_daily_loss_bps` | 50 | `risk_policy.py:11` | 0.50% |
| `max_weekly_loss_bps` | 150 | `risk_policy.py:12` | 1.50% |
| `max_total_drawdown_bps` | 300 | `risk_policy.py:13` | 3.00% |
| `max_open_positions` | 1 | `risk_policy.py:14` | |
| `max_orders_per_day` | 3 | `risk_policy.py:15` | |

**⚠️ PARAMETER CONFLICTS (flag per Phase 0.4):**
1. **`max_positions`**: `core/config.py:66` = **5**, but `risk_policy.py:14` = **1**. Two different values for "max open positions" in two frozen/policy objects. Which one governs a live order is not enforced at one point — depends on which path executes.
2. **`max_drawdown`**: `core/config.py:64` `max_drawdown_pct=10.0` vs `risk_policy.py:13` `max_total_drawdown_bps=300` (= 3.0%). **3.3× difference.** The backtest engine (`backtest/engine.py:950,955`) uses `RiskPolicy` (3%), so backtest halts at 3% DD; live path config says 10%. If live path uses config, it allows 3.3× the drawdown backtest was validated against.
3. **`mt5_server`**: default `ICMarketsSC-Demo` (`core/config.py:32`) but `.env` = `Pepperstone-Demo` (`config.yaml`/`.env:4`) and `Meta/pepperstone_creds.txt` = `Pepperstone-Demo03`. **Three different broker identities referenced.** Which broker the live system actually connects to depends on env loading at runtime — `[partly UNVERIFIED which wins]`.
4. **`BacktestConfig`** (`backtest/engine.py:129-142`) has its OWN `risk_per_trade_bps=10`, `max_positions=5`, `commission_per_lot=3.5`, `spread_pips=2.0` — **a third source of truth** for backtest specifically, independent of both `QuantConfig` and `RiskPolicy`.

**HARD_LIMITS** enforcement: `core/config.py:166-174` clamps soft limits to `HARD_LIMITS` (from `core/golden_rules.py`, not opened this phase — `[partly UNVERIFIED]`).

---

## 0.5 — Data Files on Disk

`data/` contains CSVs for **15 symbols × 9 timeframes** (M1,M5,M15,M30,H1,H4,D1,W1,MN1): XAUUSD, XAGUSD, XPDUSD, XPTUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, US30, NAS100, BTCUSD, ETHUSD.

**XAUUSD_M1.csv**: 5,000 rows, **first bar `2026-06-22 20:59:00`** (verified by reading the file). Today is 2026-06-29. **→ The M1 backtest window is ~7 days.** This is the single most important Phase-0 fact: per R18, every headline metric derived from this data describes **calm-market behavior only**, with zero tail events (no SNB/Brexit/COVID/flash-crash in a 7-day late-June-2026 window).

Other: `data/market_data.duckdb`, `data/fred/` (40 entries — FRED macro), `data/news/` (4), `data/cot/` (empty), `data/ticks/` (empty), `data/manifests/` (8).

**ForexFactory economic calendar**: referenced in code via `events/` and `news_events/` modules; `data/news/` exists but contents `[not opened this phase]`. Per Phase 25 checklist this is a live-gate item. **`[PARTIALLY UNVERIFIED — data/news/ dir exists, calendar join logic not yet traced]`.**

**Cached intermediate files**: `*.duckdb`, `data/duckdb_write_queue.py`, `results/*.json`, `ml/models/`, `fin_model/fin_model.tar.gz`, `catboost_info/`. The `.duckdb` and model artifacts are regenerable via scripts but **no content-hash / manifest lock is enforced in code that I found** — staleness risk exists (Phase 19).

---

## 0.6 — Test Coverage

**145 test files** under `tests/` plus module-local `test_*.py` scattered through `canary/`, `shadow/`, `ticks/`, `events/`, `expansion/`, `cost/`, `oracle/`, `runtime/`, `regime/`, `gold_bot/tests/`.

Notable test presence: `test_cost_unit_regression.py`, `test_lookahead_regression.py`, `test_label_shuffling.py`, `test_feature_parity.py`, `test_exit_price_correctness.py`, `test_engine_ledger_tamper.py`, `test_phase_5_cost_stress.py`, `test_phase_5_statistical.py`, `test_release_reproducibility.py`, `test_position_sizer_numeric.py` — these are exactly the tests an auditor wants to see exist. **Whether they actually test the right thing is Phase-by-Phase (existence ≠ correctness, per R-self-check #5).**

**When last run / passing**: `[NOT VERIFIED THIS SESSION]` — pytest not executed yet in this audit (planned for Phase 13/19). `QUARANTINE_MANIFEST.md` + `quarantine_manifest.json` exist (per AGENTS.md quarantine discipline).

---

## 0.7 — Compute & Runtime Environment

- **OS**: Windows 10.0.26200 x64 (per environment header).
- **Python**: requires `>=3.11` (`pyproject.toml:9`); exact installed version `[UNVERIFIED — no python --version captured]`.
- **MT5 terminal build**: `[UNVERIFIED — requires live terminal_info() call]`.
- **Host**: per `Meta/aws_deployment_guide.md`, `Meta/gcloud_deployment_guide.md`, `infra/systemd/`, `run_paper_trading.ps1`, `scripts/deploy_vps.ps1` — VPS deployment is planned/documented. **Current state (local vs VPS) `[UNVERIFIED]`.**
- **Timezone reconciliation**: `mt5_connector/connection.py:197` uses `datetime.utcnow()` for bar fetch range; `core/` has `session_manager.py`, `shadow/canonical_time_authority.py`, `mql5/terminal_time_probe.mq5`. Full reconciliation deferred to Phase 1.1.

---

## 0.8 — Process & Scheduling

- `infra/systemd/` (1 file) + `run_paper_trading.ps1` + `scripts/install_services.bat` + `scripts/setup_autostart.ps1` + `scripts/check_scheduler.ps1` — multiple scheduling mechanisms documented.
- **Watchdog distinct from bot**: `monitoring/dead_mans_switch.py` exists and is wired in `run_paper_trading.py:78-85` with `close_all_positions` + `halt_system` callbacks. Whether it is a *separate process* (survives bot crash) vs. an in-process coroutine **`[UNVERIFIED — must read dead_mans_switch.py]`** — flagged Phase 9.
- Memory/CPU limits: `[UNVERIFIED]`.

---

## 0.9 — Dependency Supply-Chain & Vulnerability

- `MetaTrader5==5.0.5735` installed source `[UNVERIFIED]`; terminal-build match `[UNVERIFIED]`.
- **`pip-audit` / vuln scan**: `[NO SCAN RUN]` — no evidence in repo.

---

## Phase 0 — Verdict

**STATUS: PARTIAL.** Census complete for structure, deps, config, data. Unverified items are runtime/external (terminal build, installed versions, host state) — blocked on live access, not on code reading. **The single decision-relevant fact from this phase: the M1 backtest data is ~7 days (2026-06-22 → 2026-06-29), so no headline Sharpe/DD from M1 data has earned the right to imply tail-event survival (R18).**
