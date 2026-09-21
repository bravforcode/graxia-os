from pathlib import Path


def test_source_deploy_builds_images_before_migration_and_startup():
    repo_root = Path(__file__).resolve().parents[1]
    deploy_script = (repo_root / "deploy" / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    script_build = deploy_script.index(
        "compose build --pull backend frontend celery_worker celery_beat"
    )
    script_migrate = deploy_script.index(
        "compose run --rm --no-deps backend python scripts/alembic_safe.py upgrade head"
    )
    script_start = deploy_script.index("compose up -d --remove-orphans --wait")

    workflow_checkout = workflow.index('git checkout --detach "${{ github.sha }}"')
    workflow_build = workflow.index(
        "$COMPOSE build --pull backend frontend celery_worker celery_beat"
    )
    workflow_migrate = workflow.index("$COMPOSE run --rm --no-deps backend alembic upgrade head")
    workflow_start = workflow.index("$COMPOSE up -d --remove-orphans --wait")

    assert script_build < script_migrate < script_start
    assert workflow_checkout < workflow_build < workflow_migrate < workflow_start


def test_production_workflow_validates_inputs_and_runs_env_audit_before_remote_compose():
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    for secret_name in ("PROD_PATH", "PROD_HOST", "PROD_USER", "PROD_SSH_KEY"):
        assert secret_name in workflow

    audit = workflow.index("python3 backend/scripts/production_env_audit.py")
    compose = workflow.index('COMPOSE="docker compose -f config/docker-compose.production.yml')
    assert audit < compose
    assert "require_env_key CADDY_EMAIL" in workflow
    assert "require_env_key APP_HOST" in workflow


def test_production_caddy_receives_required_runtime_values_without_defaults():
    repo_root = Path(__file__).resolve().parents[1]
    compose = (repo_root / "config" / "docker-compose.production.yml").read_text(encoding="utf-8")
    caddyfile = (repo_root / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "CADDY_EMAIL: ${CADDY_EMAIL:?CADDY_EMAIL is required}" in compose
    assert "APP_HOST: ${APP_HOST:?APP_HOST is required}" in compose
    assert "email {$CADDY_EMAIL}" in caddyfile
    assert "http://{$APP_HOST}" in caddyfile
    assert "https://{$APP_HOST}" in caddyfile
    assert ":admin@example.com" not in caddyfile
    assert ":app.example.com" not in caddyfile
