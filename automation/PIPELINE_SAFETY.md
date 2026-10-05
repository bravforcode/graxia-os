# Pipeline safety and rollout status

The default daily pipeline generates templates, skips Facebook publishing, and previews Meta ad objects without HTTP calls. Environment credentials alone cannot opt into paid AI or publishing. `run_daily.py --ai` explicitly opts into the existing AI path; `--live` explicitly opts into Facebook posting. Its ads step remains preview-only. Meta CLI previews both `--post` and `--ads` unless `--live` is explicitly supplied. Direct `post_to_page(body)` now previews; publishing requires `dry_run=False`. Existing in-repository callers have been updated. External callers must review this changed default.

Optional httpx imports follow no-key/no-token guards. Meta false results/exceptions produce exit 1; the orchestrator propagates positive child failures and normalizes signal failures to exit 1. It stops before success summary. Raw subprocess stderr/provider exception strings are not echoed. Workflow diff/commit/push errors now fail instead of printing an unconditional success or suppressed push message. Token permissions, secrets and schedules are unchanged.

Run bounded offline regression from repository root:

```text
python tests/test_pipeline_hardening_offline.py -v
```

Seven tests passed during local application. The suite blocks sockets/HTTP client imports, uses dummy environments, tests actual default CLI scripts in a temporary fixture, stubs all Git operations, and checks child failure propagation and no-change/commit/push/diff exits. No provider, real commit/push from tests, deployment, dependencies or paid resource is invoked. Templates and preview results are tested; rights/quality of publishable assets are not certified.

## Push trigger review (2026-10-05)

Existing remote is https://github.com/bravforcode/graxia-os.git; repository API reports public, default branch main. Fetched remote main matches reviewed base `331aa0924cb797a1359db242616c1018c53d472a`. Read-only GitHub workflow metadata reports all configured workflows active.

- `ci.yml`: main and feature-branch push; test/build jobs plus main-only container image publication. Some existing tests suppress failures. No new blanket CI-green claim is made.
- `deploy.yml`: main push builds/publishes images, runs SSH production deployment, executes Alembic migrations, restarts Docker services and sends Discord notifications. This pipeline change does not verify that destination or its business/provider/zero-cost behavior.
- `growth-ci.yml`: main push runs backend/frontend checks; no deployment command found.
- `revenue-os-quality.yml`: main push only for declared Revenue/backend/deployment safety paths. These six scoped pipeline/test/documentation files do not match its source path filters.
- `security-gate.yml`: pull-request/manual only.
- `release.yml`: v-tag push only; no tag is planned.
- `free-pipeline.yml`, `keep-alive.yml`, `cron-lead-hunter.yml`, `cron-daily-report.yml`: schedule/manual only, not triggered by this source push. The updated daily pipeline remains template/preview-only by default when later scheduled.
- GitHub dynamic Dependabot workflow is managed outside these repository files; this source push does not modify dependency manifests.

Existing parent-verified Render autodeployment watches main commits. Repository deployment state/provider effects and exact no-cost runtime were not verified through supported access in this task. A main push therefore cannot yet be cleared against the user's zero-additional-cost/no-unsafe-provider constraint. No attempt is made to bypass deployments using a skip marker, disable workflows, alter hosting or push an arbitrary branch while claiming main is updated.

Local source application/commit is authorized and complete. Push, exact-commit remote CI, automatic deployment and live business acceptance remain separately gated on evidence that the existing automatic deployment target and Render behavior are safe and impose zero additional cost. Broad push authorization is already present; the missing item is factual deployment verification, not repeated permission for the scoped repair. No supported target runtime access or validated production database is established here. Existing VPS migration remains separate. Do not touch excluded resources or backup systems to unblock it.
