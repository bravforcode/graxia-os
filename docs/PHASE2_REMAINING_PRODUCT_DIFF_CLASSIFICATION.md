# Phase 2 Remaining Product Diff Classification

## Summary
| Bucket | Count | Commit candidate | Risk |
|---|---:|---|---|
| A. Backend product implementation | 46 | backend implementation commits split by feature cluster | High |
| B. Backend tests | 30 | backend test coverage commit(s) | Medium |
| C. Frontend product/UI implementation | 53 | frontend operator UI/content UI commit(s) | High |
| D. Frontend tests/build config | 11 | frontend config/e2e/build commit | Medium |
| E. Migrations/schema | 8 | migration/schema commit | High |
| F. CI/scripts | 68 | scripts/ops/CI/staging utilities commit(s) | High |
| G. Documentation/reports | 28 | docs/report commits | Low |
| H. Generated/runtime/cache artifact | 6 | do not preserve as product code | Medium |
| I. Suspicious/stray path | 3 | hold for explicit decision | High |
| J. Unknown/human review | 8 | review before staging | High |

## A. Backend Product Implementation
| Path | Status | Likely feature | Risk | Commit group |
|---|---|---|---|---|
| `backend/app/api/auth.py` | `M` | auth hardening | High | A1 |
| `backend/app/api/approvals.py` | `M` | approval flow updates | High | A1 |
| `backend/app/api/funnel.py` | `M` | funnel integration changes | High | A2 |
| `backend/app/api/router.py` | `M` | route registration | High | A1 |
| `backend/app/api/system.py` | `M` | system endpoint updates | Medium | A1 |
| `backend/app/api/audit.py` | `??` | audit API | High | A1 |
| `backend/app/api/health.py` | `??` | health endpoint | High | A1 |
| `backend/app/auth/` | `??` | auth context/dependencies | High | A1 |
| `backend/app/core/security.py` | `M` | security behavior | High | A1 |
| `backend/app/core/security_hardening.py` | `M` | hardening | High | A1 |
| `backend/app/core/bootstrap.py` | `M` | startup/bootstrap | Medium | A3 |
| `backend/app/core/event_bus.py` | `M` | event bus/runtime behavior | Medium | A3 |
| `backend/app/core/rag.py` | `M` | retrieval behavior | Medium | A3 |
| `backend/app/agents/social/facebook_agent.py` | `M` | social/content workflow | Medium | A4 |
| `backend/app/agents/social/line_agent.py` | `M` | social/content workflow | Medium | A4 |
| `backend/app/api/content_engine.py` | `??` | content engine API | Medium | A4 |
| `backend/app/models/content_engine.py` | `??` | content engine model | Medium | A4 |
| `backend/app/services/content_engine_service.py` | `??` | content engine service | Medium | A4 |
| `backend/app/tasks/content_engine_tasks.py` | `??` | content engine tasks | Medium | A4 |
| `backend/app/services/knowledge_service.py` | `M` | knowledge/runtime writeback | Medium | A3 |

## B. Backend Tests
| Path pattern | Count | Scope | Risk | Commit group |
|---|---:|---|---|---|
| `backend/tests/test_auth_context.py` and auth/readiness/audit tests | 4 | staging/auth/readiness | High | B1 |
| `backend/tests/test_funnel_foundation.py` and funnel/MCP tests | 4 | funnel/MCP | Medium | B2 |
| `backend/tests/test_config_validation.py`, `test_csrf_*`, `test_security_features.py` | 4 | security/config | High | B1 |
| `backend/tests/test_backup_contracts.py`, `test_event_bus_*`, `test_knowledge_service.py` | 5 | runtime/knowledge/event bus | Medium | B3 |
| legacy modified tests under `backend/tests/` | 13 | mixed regression coverage | Medium | B4 |

## C. Frontend Product/UI Implementation
| Path pattern | Count | Scope | Risk | Commit group |
|---|---:|---|---|---|
| `frontend/src/pages/*.tsx` | 16 | operator dashboard/pages | High | C1 |
| `frontend/src/components/ui/*` | 18 | design system/UI layer | Medium | C2 |
| `frontend/src/components/AuthShell.tsx`, `frontend/src/contexts/AuthContext.tsx` | 2 | auth shell | High | C1 |
| `frontend/src/lib/websocket/revenue-os-ws.ts` | 1 | runtime stream client | Medium | C1 |
| `frontend/src/pages/ContentEngine.tsx` | 1 | content engine UI | Medium | C3 |
| `frontend/src/hooks/use-toast.ts` and new UI utilities | 1+ | component support | Low | C2 |

## D. Frontend Tests / Build Config
| Path pattern | Count | Scope | Risk | Commit group |
|---|---:|---|---|---|
| `frontend/package.json`, `bun.lock` | 2 | package/deps | Medium | D1 |
| `frontend/vite.config.ts`, `frontend/playwright.config.ts`, `frontend/tailwind.config.js` | 3 | build/test tooling | Medium | D1 |
| `frontend/e2e/*`, `frontend/tests/Layout.test.tsx` | 4 | e2e/layout tests | Medium | D2 |
| `frontend/components.json`, `frontend/storageState.json` | 2 | generated/local config candidates | High | J1 |

## E. Migrations / Schema
| Path | Status | Scope | Risk | Commit group |
|---|---|---|---|---|
| `backend/alembic/env.py` | `M` | env wiring | High | E1 |
| `backend/alembic/versions/001_enterprise_baseline.py` | `M` | baseline migration edits | High | E1 |
| `backend/alembic/versions/003_fix_users_table.py` | `M` | schema fix | High | E1 |
| `backend/alembic/versions/019_content_engine.py` | `??` | content engine schema | High | E2 |
| `backend/alembic/versions/020_add_funnel_foundation.py` | `??` | funnel schema | High | E2 |
| `backend/alembic/versions/1e9db9a3b0ba_merge_funnel_foundation_and_performance_.py` | `??` | merge head | High | E2 |
| `backend/alembic/versions/6dd9193e3e73_add_tenancy_performance_indexes.py` | `??` | tenancy/performance | High | E2 |
| `backend/alembic/versions/cef7acf8e4ed_final_head_merge.py` | `??` | final merge head | High | E2 |

## F. CI / Scripts
| Path pattern | Count | Scope | Risk | Commit group |
|---|---:|---|---|---|
| `.github/workflows/*.yml` | 2 | CI/deploy workflow | Medium | F1 |
| `scripts/check_staging_readiness.*`, `scripts/staging_smoke.*` | 4 | staging readiness utilities | High | F2 |
| `scripts/ops/*` | 30+ | ops tooling | Medium | F3 |
| `config/docker-compose*.yml`, `docker-compose.yml` | 3 | runtime compose | High | F4 |
| `.env.example` | 1 | env template | High | F1 |
| `backend/scripts/*`, `backend/init_viewing_db.py` | 3+ | backend ops | Medium | F3 |

## G. Documentation
| Path pattern | Count | Scope | Risk | Commit group |
|---|---:|---|---|---|
| `docs/*.md` | 20+ | operational/project docs | Low | G1 |
| `README.md`, `AGENTS.md`, `CLAUDE.md` | 3 | root guidance/docs | Low | G1 |
| `04-Archive/phase-reports/MIGRATION_INSTRUCTIONS_TH.md` | 1 | archived report | Low | G1 |

## H. Generated / Runtime / Cache Artifact
| Path | Status | Notes | Action |
|---|---|---|---|
| `.hypothesis/` | `??` | local test artifact | do not stage |
| `backend/.hypothesis/` | `??` | local test artifact | do not stage |
| `backups/` | `??` | runtime backup output | do not stage |
| `.lean-ctx-init` | `??` | local tool artifact | do not stage |
| `.openclaude-profile.json` | `??` | local tool artifact | do not stage |
| `.testsprite.json` | `??` | local tool artifact | do not stage |

## I. Suspicious / Stray Path
| Path | Status | Why suspicious | Recommended action |
|---|---|---|---|
| `"ersmenumgraxia os\\357\\200\\242 && git status"` | `D` | tracked file name appears to contain pasted shell text / mojibake | do not auto-stage; require explicit decision |
| `backend/nul` | `??` | reserved Windows device-like name | inspect as suspicious, do not auto-stage |
| `nul` | `??` | reserved Windows device-like name | inspect as suspicious, do not auto-stage |

## J. Unknown / Human Review
| Path | Status | Why held | Suggested handling |
|---|---|---|---|
| `backend/requirements.txt` | `M` | dep changes may span multiple feature groups | hold until backend grouping decided |
| `.agents/` | `??` | local agent framework files | hold |
| `.planning/` | `??` | local planning metadata | hold |
| `LEAN-CTX.md` | `??` | local tooling doc | hold |
| `backend/seed_real_user.py` | `??` | unclear if local-only or product ops | hold |
| `extraterrestrial-escape/` | `??` | unrelated subtree risk | hold |
| `sites/` | `??` | unrelated subtree risk | hold |

## Proposed Commit Groups
1. `P2-docs` — classification/strategy/test-plan docs only.
2. `A1/B1` — backend auth/health/audit/auth-context implementation + matching tests.
3. `A3/B3` — backend bootstrap/event-bus/knowledge/runtime behavior + matching tests.
4. `A4/E2` — content-engine/social backend + matching migrations/tests if tightly coupled.
5. `C1/C2/D1/D2` — frontend operator UI/build/test changes.
6. `F1/F2/F3/F4` — CI, compose, ops, staging scripts.
7. `G1` — root/docs/report changes.
8. `I/J` — suspicious/unknown paths only after explicit review.
