import re
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


def test_production_deploy_is_main_ref_gated_and_ssh_action_is_immutable():
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    deploy_job = workflow.index("\n  deploy:\n")
    deploy_guard = workflow.index("if: github.ref == 'refs/heads/main'", deploy_job)
    deploy_steps = workflow.index("\n    steps:\n", deploy_job)

    assert deploy_guard < deploy_steps
    assert (
        "uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2"
        in workflow
    )
    assert "uses: appleboy/ssh-action@v1" not in workflow


def test_production_build_and_latest_publication_are_main_ref_gated_and_pinned():
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    build_job = workflow.index("\n  build:\n")
    build_guard = workflow.index("if: github.ref == 'refs/heads/main'", build_job)
    build_steps = workflow.index("\n    steps:\n", build_job)
    deploy_job = workflow.index("\n  # ─── Deploy", build_job)
    build_body = workflow[build_job:deploy_job]

    assert build_guard < build_steps
    assert "${{ env.BACKEND_IMAGE }}:latest" in build_body
    assert "${{ env.FRONTEND_IMAGE }}:latest" in build_body

    expected_actions = [
        ("actions/checkout", "11bd71901bbe5b1630ceea73d27597364c9af683"),
        ("docker/login-action", "74a5d142397b4f367a81961eba4e8cd7edddf772"),
        ("docker/setup-buildx-action", "6524bf65af31da8d45b59e8c27de4bd072b392f5"),
        ("docker/build-push-action", "ca052bb54ab0790a636c9b5f226502c73d547a25"),
        ("docker/build-push-action", "ca052bb54ab0790a636c9b5f226502c73d547a25"),
        ("actions/upload-artifact", "ea165f8d65b6e75b540449e92b4886f43607fa02"),
        ("actions/download-artifact", "d3f86a106a0bac45b974a628896c90dbdf5c8093"),
        ("appleboy/ssh-action", "0ff4204d59e8e51228ff73bce53f80d53301dee2"),
    ]
    action_refs = re.findall(r"^\s+uses:\s+([^@\s]+)@([^\s]+)$", workflow, re.MULTILINE)

    assert action_refs == expected_actions
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for _, sha in action_refs)


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
