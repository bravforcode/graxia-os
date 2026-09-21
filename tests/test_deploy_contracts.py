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
