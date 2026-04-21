import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from scripts.production_env_audit import audit_production_env


WRITABLE_TEMP_ROOT = Path("C:/Users/menum/.codex/memories/tmp/bravos-prodready-tests")


def _valid_env_values() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "APP_HOST": "app.bravos.ai",
        "CADDY_EMAIL": "ops@bravos.ai",
        "SECRET_KEY": "prod-secret-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4Y5z6",
        "ENCRYPTION_KEY": "enc-key-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0",
        "JWT_SIGNING_KEYS": '{"v1":"jwt-signing-key-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4Y5z6"}',
        "JWT_ACTIVE_KID": "v1",
        "JWT_ISSUER": "personal-os",
        "JWT_AUDIENCE": "personal-os-api",
        "CSRF_SECRET": "csrf-secret-A1b2C3d4E5f6G7h8I9j0",
        "REQUIRE_SUPABASE": "true",
        "SUPABASE_URL": "https://bravos-prod.supabase.co",
        "SUPABASE_ANON_KEY": "sb_publishable_prod_key_A1b2C3d4E5f6",
        "SUPABASE_SERVICE_ROLE_KEY": "sb_service_role_prod_key_A1b2C3d4E5f6",
        "DATABASE_URL": "postgresql://postgres.bravos-prod:postgres-prod-pass@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require",
        "DATABASE_MIGRATION_URL": "postgresql://postgres:postgres-prod-pass@db.bravos-prod.supabase.co:5432/postgres?sslmode=require",
        "POSTGRES_PASSWORD": "postgres-prod-pass",
        "REDIS_URL": "redis://:redis-prod-pass@redis.prod.internal:6379/0",
        "CELERY_BROKER_URL": "redis://:redis-prod-pass@redis.prod.internal:6379/1",
        "CELERY_RESULT_BACKEND": "redis://:redis-prod-pass@redis.prod.internal:6379/2",
        "APP_BASE_URL": "https://api.bravos.ai",
        "FRONTEND_URL": "https://app.bravos.ai",
        "ALLOWED_CORS_ORIGINS": "https://app.bravos.ai",
        "TELEGRAM_BOT_TOKEN": "123456:AAprodTokenWithEnoughEntropyForValidation",
        "TELEGRAM_CHAT_ID": "123456789",
        "ALERTMANAGER_WEBHOOK_TOKEN": "alertmanager-prod-token-A1b2C3d4E5f6",
        "BACKUP_BUCKET": "bravos-prod-backups",
        "BACKUP_REGION": "ap-southeast-1",
        "BACKUP_ENCRYPTION_PUBLIC_KEY": "age1prodpublickeymaterial",
        "BACKUP_ENCRYPTION_PRIVATE_KEY_FILE": "/secure/bravos-backup.key",
        "N8N_PASSWORD": "n8n-prod-password-A1b2C3d4",
        "FLOWER_BASIC_AUTH": "admin:flower-prod-password-A1b2C3d4",
        "GRAFANA_ADMIN_PASSWORD": "grafana-prod-password-A1b2C3d4",
    }


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


def _write_secret_files(repo_root: Path) -> None:
    secrets_dir = repo_root / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "backup_private_key.txt").write_text("AGE-SECRET-KEY-TEST-ONLY\n", encoding="utf-8")
    (secrets_dir / "alertmanager_webhook_token.txt").write_text("alertmanager-secret-token\n", encoding="utf-8")


@contextmanager
def _temp_workspace():
    WRITABLE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    workspace = WRITABLE_TEMP_ROOT / uuid4().hex
    workspace.mkdir()
    try:
        yield str(workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_production_env_audit_passes_with_strict_env_and_frontend_bridge():
    with _temp_workspace() as temp_dir:
        tmp_path = Path(temp_dir)
        env_file = tmp_path / ".env.production"
        compose_file = tmp_path / "docker-compose.supabase.yml"
        frontend_env_file = tmp_path / "frontend.env.production"

        _write_env_file(env_file, _valid_env_values())
        _write_secret_files(tmp_path)
        compose_file.write_text(
            """
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: ${APP_BASE_URL}/api/v1
        VITE_AGENT_STREAM_URL: wss://${APP_HOST}/api/v1/events/stream
        VITE_SUPABASE_URL: ${SUPABASE_URL}
        VITE_SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
""".strip(),
            encoding="utf-8",
        )
        frontend_env_file.write_text(
            "VITE_API_BASE_URL=https://your-domain.com/api/v1\nVITE_AGENT_STREAM_URL=wss://your-domain.com/api/v1/events/stream\n",
            encoding="utf-8",
        )

        result = audit_production_env(
            env_file,
            compose_file,
            frontend_env_file=frontend_env_file,
            repo_root=tmp_path,
        )

        assert result.failed == 0
        assert any("frontend/.env.production still contains placeholder values" in warning for warning in result.warnings)


def test_production_env_audit_fails_when_frontend_supabase_bridge_is_missing():
    with _temp_workspace() as temp_dir:
        tmp_path = Path(temp_dir)
        env_file = tmp_path / ".env.production"
        compose_file = tmp_path / "docker-compose.supabase.yml"

        _write_env_file(env_file, _valid_env_values())
        _write_secret_files(tmp_path)
        compose_file.write_text(
            """
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: ${APP_BASE_URL}/api/v1
""".strip(),
            encoding="utf-8",
        )

        result = audit_production_env(env_file, compose_file, repo_root=tmp_path)

        assert result.failed >= 1
        assert any(name == "compose bridge VITE_SUPABASE_URL" and not ok for name, ok, _message in result.checks)


def test_production_env_audit_fails_when_required_secret_files_are_missing():
    with _temp_workspace() as temp_dir:
        tmp_path = Path(temp_dir)
        env_file = tmp_path / ".env.production"
        compose_file = tmp_path / "docker-compose.supabase.yml"

        _write_env_file(env_file, _valid_env_values())
        compose_file.write_text(
            """
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: ${APP_BASE_URL}/api/v1
        VITE_AGENT_STREAM_URL: wss://${APP_HOST}/api/v1/events/stream
        VITE_SUPABASE_URL: ${SUPABASE_URL}
        VITE_SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
""".strip(),
            encoding="utf-8",
        )

        result = audit_production_env(env_file, compose_file, repo_root=tmp_path)

        assert result.failed >= 1
        assert any(name == "secret file backup_private_key.txt" and not ok for name, ok, _message in result.checks)
