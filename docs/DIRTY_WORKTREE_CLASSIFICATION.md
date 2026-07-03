# Dirty Worktree Classification

## Summary
| Bucket | Count | Risk |
|---|---:|---|
| A. Product Source Changes | 112 | high |
| B. Test Changes | 34 | medium |
| C. Documentation Changes | 29 | low |
| D. Migration / Schema Changes | 8 | high |
| E. Frontend Source Changes | 57 | high |
| F. Generated Artifacts | 3 | medium |
| G. Virtualenv / Dependency / Vendor Artifacts | 111 | high |
| H. Runtime / Cache / Log Artifacts | 8 | medium |
| I. Unknown / Requires Human Review | 17 | high |

## A. Product Source Changes
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `backend/app/agents/research_collector.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/agents/social/facebook_agent.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/agents/social/line_agent.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/agents/vault_indexer.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/ai/client.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/approvals.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/audit.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/auth.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/contacts.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/content_engine.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/funnel.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/health.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/onboarding.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/router.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/api/system.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/auth/__init__.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/auth/context.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/auth/dependencies.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/auth/errors.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/auth/middleware.py` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/bootstrap.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/event_bus.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/rag.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/security_hardening.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/security.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/setup.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/core/unit_of_work.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/database.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/integrations/salesforce.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/main.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/mcp/tools/funnel.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/mcp/tools/write.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/middleware/auth.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/middleware/security.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/approval_request.py` | `M ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/content_engine.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/email_thread.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/job_posting.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/opportunity.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/submission.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/models/user.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/schemas/content_engine.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/scrapers/facebook.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/services/content_engine_service.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/services/email_service.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/services/knowledge_service.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/tasks/backup_tasks.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/tasks/celery_app.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/tasks/content_engine_tasks.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/app/tasks/schedule.py` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/init_viewing_db.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/requirements.txt` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/scripts/__init__.py` | ` D` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/scripts/verify_tenancy_indexes.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `backend/seed_real_user.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `config/docker-compose.dev.yml` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `config/docker-compose.production.yml` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `config/README.md` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `docker-compose.yml` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `Makefile` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/__init__.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/check_staging_readiness.ps1` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/check_staging_readiness.sh` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/legacy/` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/__init__.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/alembic_safe.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/approve_task.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/backup_database.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/backup_database.sh` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/benchmark_queries.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/check_destructive_migrations.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/check_meta.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/clear_test_data.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/current_migration.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/db_index_audit.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/enterprise_readiness.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/export_leads_json.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/export_openapi.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/fix_vector_dim.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/generate_route_manifest.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/import_contacts.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/init_db.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/inject_massive_data.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/production_env_audit.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/production_preflight.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/record_deploy.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/restore_database.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/restore_database.sh` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/run_backend.bat` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/run_security_baseline.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/run_server.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/scraper_recovery.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/skills_api_gateway.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/smoke_test_production.sh` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/smoke_tests.sh` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/soak_monitor.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/suggest_outreach_allowlist.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/test_webhook_signature.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/test_webhook.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/validate_production_config.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_csrf_fix.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_graceful_shutdown.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_indexes.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_mas_autonomy.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_queue_limits.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_secrets_validation.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_system.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/ops/verify_webhook_hmac.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/staging_smoke.ps1` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/staging_smoke.sh` | `A ` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `scripts/tests/patch_chaos_tests.py` | `??` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |
| `vercel.json` | ` M` | high | Review | Backend/product/config change; preserve but isolate from hygiene cleanup. |

## B. Test Changes
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `backend/tests/factories.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/integration/test_knowledge_service.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_approval_flow_contracts.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_approval_org_scope.py` | `A ` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_audit_query.py` | `A ` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_auth_context.py` | `A ` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_backup_contracts.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_billing.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_bootstrap_contract.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_chaos_resilience.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_config_validation.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_csrf_expiry.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_csrf_timing.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_email_service.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_env_example_safety.py` | `A ` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_event_bus_backpressure.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_event_bus_shutdown.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_funnel_foundation.py` | `??` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_health_readiness.py` | `A ` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_migration_018.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_onboarding.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_operations_api_contracts.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_production_env_audit.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_security_features.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_soft_delete_contracts.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_tenancy.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/test_tooling_contracts.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `backend/tests/unit/test_workflow_service.py` | `??` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `frontend/e2e/app-shell.spec.ts` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `frontend/e2e/chaos/` | `??` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `frontend/e2e/global-setup.ts` | `??` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `frontend/tests/Layout.test.tsx` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `tests/test_api_integration.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |
| `tests/test_api_security.py` | ` M` | medium | Review | Test coverage or verification work; split from runtime import later. |

## C. Documentation Changes
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `04-Archive/phase-reports/MIGRATION_INSTRUCTIONS_TH.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `AGENTS.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `CLAUDE.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/AGENTS.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/API_DOCUMENTATION.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/ARCHITECTURE.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/CSRF_FIX_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_1.2_COMPLETION_REPORT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.1_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.2_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.2_SUMMARY.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.3_CHECKLIST.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.3_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.3_QUICK_REFERENCE.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.3_SUMMARY.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.4_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.4_SUMMARY.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/TASK_2.5_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/archive/WEBHOOK_HMAC_DEPLOYMENT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/audits/2026-05-07-graxia-ultra-audit.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/CROSS_REPO_MERGE_AUDIT.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/DEPLOYMENT.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/FINAL_VERIFICATION_REPORT.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/INSTRUCTIONS.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/OPERATIONAL_RUNBOOK.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/PRE_DEVELOPMENT_CHECKLIST.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `docs/SKILLSMP_INTEGRATION_GUIDE.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `LEAN-CTX.md` | `??` | low | Review | Docs/process change; safe to keep in separate docs commit. |
| `README.md` | ` M` | low | Review | Docs/process change; safe to keep in separate docs commit. |

## D. Migration / Schema Changes
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `backend/alembic/env.py` | ` M` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/001_enterprise_baseline.py` | ` M` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/003_fix_users_table.py` | ` M` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/019_content_engine.py` | `??` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/020_add_funnel_foundation.py` | `??` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/1e9db9a3b0ba_merge_funnel_foundation_and_performance_.py` | `??` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/6dd9193e3e73_add_tenancy_performance_indexes.py` | `??` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |
| `backend/alembic/versions/cef7acf8e4ed_final_head_merge.py` | `??` | high | Review | Schema/migration diff; keep separate from hygiene cleanup. |

## E. Frontend Source Changes
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `frontend/package.json` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/playwright.config.ts` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/AuthShell.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/canvas/AgentCanvas.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ControlPlaneUnavailable.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/layout/CommandBar.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/activity-feed.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/animated-tooltip.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/button.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/button.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/card.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/command.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/dialog.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/dialog.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/dropdown-menu.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/empty-state.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/glass-card.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/input.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/label.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/metric-card.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/notice-banner.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/notice-banner.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/page-header.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/scroll-area.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/select.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/sheet.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/status-pill.stories.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/tabs.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/theme-toggle.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/toast.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/components/ui/toaster.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/contexts/AuthContext.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/hooks/use-toast.ts` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/hooks/useGraxiaStream.ts` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/index.css` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/lib/websocket/revenue-os-ws.ts` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/main.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Agents.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/ApprovalQueue.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Contacts.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/ContentEngine.tsx` | `??` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Costs.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Drafts.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/EmailThreads.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/EventBus.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Jobs.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Leads.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Login.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Metrics.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Onboarding.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Opportunities.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Register.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Settings.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/Tasks.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/src/pages/UnifiedDashboard.tsx` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/tailwind.config.js` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |
| `frontend/vite.config.ts` | ` M` | high | Review | Frontend source/config change; preserve but isolate from hygiene cleanup. |

## F. Generated Artifacts
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `.testsprite.json` | `??` | medium | No | Generated output; verify whether reproducible before keeping. |
| `backend/openapi.json` | ` M` | medium | Review | Generated output; verify whether reproducible before keeping. |
| `frontend/components.json` | `??` | medium | No | Generated output; verify whether reproducible before keeping. |

## G. Virtualenv / Dependency / Vendor Artifacts
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `.venv/Scripts/python.exe` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `.venv/Scripts/pythonw.exe` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core-2.18.1.dist-info/INSTALLER` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core-2.18.1.dist-info/license_files/LICENSE` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core-2.18.1.dist-info/METADATA` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core-2.18.1.dist-info/RECORD` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core-2.18.1.dist-info/WHEEL` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core/__init__.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core/_pydantic_core.pyi` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic_core/core_schema.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic-2.7.0.dist-info/INSTALLER` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic-2.7.0.dist-info/licenses/LICENSE` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic-2.7.0.dist-info/METADATA` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic-2.7.0.dist-info/RECORD` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic-2.7.0.dist-info/REQUESTED` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic-2.7.0.dist-info/WHEEL` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/__init__.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_config.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_core_metadata.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_core_utils.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_dataclasses.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_decorators_v1.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_decorators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_discriminated_union.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_docs_extraction.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_fields.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_generate_schema.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_generics.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_git.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_internal_dataclass.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_known_annotated_metadata.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_mock_val_ser.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_model_construction.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_repr.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_schema_generation_shared.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_signature.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_std_types_schema.py` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_typing_extra.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_utils.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_validate_call.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_internal/_validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/_migration.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/alias_generators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/aliases.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/annotated_handlers.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/class_validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/color.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/config.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/dataclasses.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/datetime_parse.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/decorator.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/deprecated/class_validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/deprecated/config.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/deprecated/copy_internals.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/deprecated/decorator.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/deprecated/json.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/deprecated/tools.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/env_settings.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/error_wrappers.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/errors.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/fields.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/functional_serializers.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/functional_validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/generics.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/json_schema.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/json.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/main.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/mypy.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/networks.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/parse.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/plugin/__init__.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/plugin/_loader.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/plugin/_schema_validator.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/root_model.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/schema.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/tools.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/type_adapter.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/types.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/typing.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/utils.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/__init__.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/_hypothesis_plugin.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/annotated_types.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/class_validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/color.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/config.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/dataclasses.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/datetime_parse.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/decorator.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/env_settings.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/error_wrappers.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/errors.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/fields.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/generics.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/json.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/main.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/mypy.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/networks.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/parse.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/schema.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/tools.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/types.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/typing.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/utils.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/v1.py` | ` D` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/v1/version.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/validate_call_decorator.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/validators.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/version.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |
| `backend/venv/Lib/site-packages/pydantic/warnings.py` | ` M` | high | No | Tracked or untracked vendor/virtualenv artifact; remove from git index only after approval. |

## H. Runtime / Cache / Log Artifacts
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `.hypothesis/` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `.lean-ctx-init` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `.planning/` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `backend/.hypothesis/` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `backend/nul` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `debug_connectivity.py` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `frontend/storageState.json` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |
| `nul` | `??` | medium | No | Local runtime/cache/log artifact; should stay out of reviewable product history. |

## I. Unknown / Requires Human Review
| Path | Status | Risk | Keep? | Notes |
|---|---|---|---|---|
| `.agents/` | `??` | high | Review | Needs human review before cleanup or import. |
| `.env.development` | `??` | high | Review | Secret-like env path present; do not read contents, decide ignore policy first. |
| `.env.example` | `M ` | high | Review | Secret-like env path present; do not read contents, decide ignore policy first. |
| `.github/workflows/ci.yml` | ` M` | high | Review | Needs human review before cleanup or import. |
| `.github/workflows/deploy.yml` | ` M` | high | Review | Needs human review before cleanup or import. |
| `.gitignore` | ` M` | high | Review | Needs human review before cleanup or import. |
| `.openclaude-profile.json` | `??` | high | Review | Needs human review before cleanup or import. |
| `"ersmenumgraxia os\357\200\242 && git status"` | ` D` | high | Review | Needs human review before cleanup or import. |
| `backups/` | `??` | high | Review | Needs human review before cleanup or import. |
| `bun.lock` | ` M` | high | Review | Needs human review before cleanup or import. |
| `extraterrestrial-escape/` | `??` | high | Review | Needs human review before cleanup or import. |
| `knowledge.md` | `??` | high | Review | Needs human review before cleanup or import. |
| `n8n/workflows/content_engine_pipeline.json` | `??` | high | Review | Needs human review before cleanup or import. |
| `sites/` | `??` | high | Review | Needs human review before cleanup or import. |
| `start-backend-simple.ps1` | `??` | high | Review | Needs human review before cleanup or import. |
| `start-graxia-ai-complete.ps1` | `??` | high | Review | Needs human review before cleanup or import. |
| `test_db.py` | `??` | high | Review | Needs human review before cleanup or import. |

## Recommended Next Actions
- Separate `G` and `H` from product review before any runtime import.
- Treat `A`, `D`, and `E` as preserved user/product work, not cleanup targets.
- Review secret-like untracked env paths without reading contents, then decide ignore/handling policy.

