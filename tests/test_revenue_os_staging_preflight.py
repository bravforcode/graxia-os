from scripts.revenue_os.staging_preflight import check_staging_environment


def _ready_env():
    return {
        "APP_ENV": "staging",
        "NO_LIVE_PAYMENT_MODE": "true",
        "KILL_SWITCH_ALL_EXTERNAL_BETA": "true",
        "DATABASE_URL": "postgresql://redacted",
        "CELERY_BROKER_URL": "redis://redacted/1",
        "CELERY_RESULT_BACKEND": "redis://redacted/2",
        "ADMIN_API_KEY": "test-admin-key",
        "STRIPE_SECRET_KEY": "sk_test_redacted",
        "STRIPE_WEBHOOK_SECRET": "whsec_redacted",
    }


def test_ready_profile_is_safe_without_provider_calls():
    report = check_staging_environment(_ready_env())

    assert report["ok"] is True
    assert report["provider_calls_performed"] is False
    assert all(report["configured"].values())


def test_missing_secret_is_blocked_and_not_echoed():
    env = _ready_env()
    env.pop("STRIPE_WEBHOOK_SECRET")

    report = check_staging_environment(env)

    assert report["ok"] is False
    assert "missing STRIPE_WEBHOOK_SECRET" in report["blockers"]
    assert "whsec_redacted" not in str(report)


def test_live_key_is_blocked():
    env = _ready_env()
    env["STRIPE_SECRET_KEY"] = "sk_live_redacted"

    report = check_staging_environment(env)

    assert report["ok"] is False
    assert "STRIPE_SECRET_KEY must be test mode" in report["blockers"]


def test_kill_switches_fail_closed():
    env = _ready_env()
    env["NO_LIVE_PAYMENT_MODE"] = "false"
    env["KILL_SWITCH_ALL_EXTERNAL_BETA"] = "false"

    report = check_staging_environment(env)

    assert report["ok"] is False
    assert len(report["blockers"]) == 2
