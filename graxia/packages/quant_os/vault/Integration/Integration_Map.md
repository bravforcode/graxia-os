# Integration Map — Vault ↔ quant_os

> The vault **indexes**, never duplicates. Numbers live in `../research/` and `../reports/`; judgment + links live in the vault.
> Relative links (`../...`) open the source file from Obsidian. Update the source → the link still resolves.

## A. Hypotheses ↔ research/
| Vault note (folder) | External artifact | Link field |
|---|---|---|
| `Hypotheses/pre-registered/*.md` | `research/pre_registration/trial_XXXX_*.md` | `pre_reg_doc` |
| `Hypotheses/*` | `research/hypothesis_registry.json` | `registry_ref` |
| `Hypotheses/candidates/*` | `research/generation_framework.md` (7 cats) | `category` tag |
| `Hypotheses/*` | `research/trial_ledger.json` (DSR count) | `dsr_cumulative_at_test` |
| All | `research/academic_gold_price_research.md` | seeded `[[Paper: ...]]` notes |

**7 framework categories** (from `generation_framework.md`) → `#domain/` tags:
`cross-asset-momentum · vol-risk-premium · session-pattern · orderflow · macro-regime · carry-momentum · mean-reversion`
+ extensions: `ml-forecasting · safe-haven · microstructure · sentiment · volatility · crypto · macro`

## B. Experiments ↔ reports/
| Vault note | External artifact | Why |
|---|---|---|
| `Experiments/EXP-XXXX.md` | `reports/pooled_trend_strategies_results.json` etc. | authoritative metrics |
| `Experiments/EXP-XXXX.md` | `reports/pre_registered_criteria.txt` | EURUSD RSI+BB gates |
| `Experiments/EXP-XXXX.md` | `reports/edge_search_cross_sectional_20260720.json` | multi-asset TSMOM evidence |
| `MOC_Rejected` | `research/hypothesis_registry.json` | 14 trials, all REJECTED |
| `Experiments/*` | `FOREX_EDGE_INVESTIGATION.md` | FX cost-dominance root cause |

**The 14 dead-end trials** (registry → vault `Hypotheses/rejected/` + `Experiments/`):
`1001 RYDC · 1003 CAM · 1004 SP · 1005 MRM · 1006 GSS · 1007 BVC · 1008 CVR · 1022 MULTI-ASSET-TSMOM · 1023 ETH-VOL · 1024 BTC-ETH · 1025 COT · 1026 FOMC · 1027 FUNDING`

## C. Data ↔ research/alternative_gold_data_sources.md
| Vault note | Source section | Integration field |
|---|---|---|
| `Data/*.md` | `research/alternative_gold_data_sources.md` §1–§10 | `quant_os_integration` |
| e.g. `Data/DFII5_RealYield.md` | §1 Missing HIGH PRIORITY | `source: "core/data/fred_client.py"` |

**10 data categories** (→ `Data/` notes): macro-indicators · positioning · sentiment · physical-market · central-bank · mining · geopolitical · onchain · orderbook-microstructure · seasonality.

## D. Tooling ↔ DEEP_RESEARCH_QUANT_STRATEGIES.md
| Vault note | Source | Field |
|---|---|---|
| `Tooling/*.md` | `DEEP_RESEARCH_QUANT_STRATEGIES.md` §1–§10 + Top-10 | `priority_rank`, `pypi` |
| e.g. `Tooling/pandas-ta.md` | §3.1 | `quant_os_use: "replace custom RSI/EMA/Bollinger"` |

**Top-10 to adopt:** pandas-ta · ccxt · statsmodels · PyPortfolioOpt · Riskfolio-Lib · vaderSentiment · alpaca-py · nevergrad · nautilus-trader · mpl-finance.

## E. Sync Rules (so the two never drift)
1. **Registry is source of truth for verdicts.** When `hypothesis_registry.json` flips a trial to REJECTED, update the matching `Hypotheses/` note: `status: rejected`, fill `root_cause_if_rejected`, and set `rejected_by: [trial_id]` on each linked `[[Paper: ...]]`.
2. **New paper read → new `Papers/` note** from `T_Paper.md`, linked from today's `Daily/` note.
3. **New pre-registration → `Hypotheses/pre-registered/`** from `T_Hypothesis.md`, `linked_papers` set.
4. **New trial run → `Experiments/`** from `T_Experiment.md`, `hypothesis_ref` + `evidence_artifact` set.
5. **Weekly:** run Dataview queries **C, I, M** to catch orphaned hypotheses (no paper) and unlogged rejects.
