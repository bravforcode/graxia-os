import pytest

from app.config import Settings


def _valid_production_settings(**overrides):
    values = {
        "APP_ENV": "production",
        "APP_HOST": "app.bravos.ai",
        "CADDY_EMAIL": "ops@bravos.ai",
        "SECRET_KEY": "prod-secret-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4Y5z6",
        "ENCRYPTION_KEY": "enc-key-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0",
        "JWT_SIGNING_KEYS": '{"v1":"jwt-signing-key-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4Y5z6"}',
        "SUPABASE_URL": "https://bravos-prod.supabase.co",
        "SUPABASE_ANON_KEY": "sb_publishable_prod_key_A1b2C3d4E5f6",
        "SUPABASE_SERVICE_ROLE_KEY": "sb_service_role_prod_key_A1b2C3d4E5f6",
        "TELEGRAM_BOT_TOKEN": "123456:AAprodTokenWithEnoughEntropyForValidation",
        "TELEGRAM_CHAT_ID": "123456789",
        "ALERTMANAGER_WEBHOOK_TOKEN": "alertmanager-prod-token-A1b2C3d4E5f6",
        "BACKUP_BUCKET": "bravos-prod-backups",
        "BACKUP_REGION": "ap-southeast-1",
        "BACKUP_ENCRYPTION_PUBLIC_KEY": "age1prodpublickeymaterial",
        "BACKUP_ENCRYPTION_PRIVATE_KEY_FILE": "/secure/bravos-backup.key",
        "N8N_PASSWORD": "n8n-prod-password-A1b2C3d4",
        "GRAFANA_ADMIN_PASSWORD": "grafana-prod-password-A1b2C3d4",
        "FLOWER_BASIC_AUTH": "admin:flower-prod-password-A1b2C3d4",
        "REDIS_URL": "redis://:redis-prod-pass-A1b2C3@redis.prod.internal:6379/0",
        "CELERY_BROKER_URL": "redis://:redis-prod-pass-A1b2C3@redis.prod.internal:6379/1",
        "CELERY_RESULT_BACKEND": "redis://:redis-prod-pass-A1b2C3@redis.prod.internal:6379/2",
        "APP_BASE_URL": "https://api.bravos.ai",
        "FRONTEND_URL": "https://app.bravos.ai",
        "ALLOWED_CORS_ORIGINS": "https://app.bravos.ai",
        "POSTGRES_PASSWORD": "postgres-prod-pass-A1b2C3",
    }
    values.update(overrides)
    return Settings(**values)


def test_development_configuration_does_not_run_strict_secret_gate():
    settings = Settings(APP_ENV="development", SECRET_KEY="short-dev-secret")

    settings.validate_production_configuration()


def test_production_configuration_rejects_placeholder_secrets_at_startup():
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY="development-secret-key-change-me",
        JWT_SIGNING_KEYS='{"v1":"development-secret-key-change-me"}',
    )

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_production_configuration()

    message = str(exc_info.value)
    assert "Production security configuration is invalid" in message
    assert "SECRET_KEY" in message
    assert "JWT signing key" in message


def test_production_configuration_rejects_invalid_jwt_keyset_json_with_escape_hint():
    settings = _valid_production_settings(
        JWT_SIGNING_KEYS=r'{"v1":"jwt-signing-key-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4Y5z6\2broken"}'
    )

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_production_configuration()

    message = str(exc_info.value)
    assert "JWT_SIGNING_KEYS must be valid JSON" in message
    assert "escape literal backslashes" in message


def test_production_configuration_rejects_wildcard_cors_origins():
    settings = _valid_production_settings(ALLOWED_CORS_ORIGINS="*")

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_production_configuration()

    assert "ALLOWED_CORS_ORIGINS must contain only explicit production origins" in str(exc_info.value)


def test_placeholder_detection_catches_frontend_and_example_placeholders():
    settings = Settings()

    assert settings._looks_placeholder("https://your-project-ref.supabase.co") is True
    assert settings._looks_placeholder("https://your-domain.com/api/v1") is True
    assert settings._looks_placeholder("ops@example.com") is True
    assert settings._looks_placeholder("https://app.bravos.ai") is False


def test_production_configuration_rejects_placeholder_deploy_contract_values():
    settings = _valid_production_settings(
        APP_HOST="https://PASTE_YOUR_DOMAIN_HERE",
        CADDY_EMAIL="admin@example.com",
        FLOWER_BASIC_AUTH="admin:REPLACE_WITH_STRONG_FLOWER_PASSWORD",
        BACKUP_REGION="PASTE_BACKUP_REGION_HERE",
    )

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_production_configuration()

    message = str(exc_info.value)
    assert "APP_HOST must be a real production hostname" in message
    assert "CADDY_EMAIL" in message
    assert "FLOWER_BASIC_AUTH" in message
    assert "BACKUP_REGION" in message


def test_migration_session_mode_is_detected_from_supabase_pooler_url():
    settings = Settings(
        DATABASE_URL="postgresql://user:pass@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require",
        DATABASE_MIGRATION_URL="postgresql://user:pass@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require",
    )

    assert settings.IS_SUPABASE_SESSION_MODE is True
    assert settings.IS_MIGRATION_SUPABASE_SESSION_MODE is True
