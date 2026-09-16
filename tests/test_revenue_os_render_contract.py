from pathlib import Path

import pytest


yaml = pytest.importorskip("yaml")
ROOT = Path(__file__).parents[1]


def _render():
    return yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))


def _service(config, name):
    return next(item for item in config["services"] if item["name"] == name)


def _env_map(service):
    result = {}
    for item in service.get("envVars", []):
        result[item["key"]] = item
    return result


def test_staging_revenue_os_isolated_and_kill_switched():
    config = _render()
    production = _service(config, "graxia-revenue-os")
    staging_names = {
        "graxia-revenue-os-staging",
        "graxia-revenue-os-staging-worker",
        "graxia-revenue-os-staging-beat",
    }
    services = {item["name"]: item for item in config["services"]}
    assert staging_names <= services.keys()
    assert production["dockerfilePath"] == services["graxia-revenue-os-staging"]["dockerfilePath"]

    for name in staging_names:
        service = services[name]
        env = _env_map(service)
        assert service["autoDeploy"] is False
        assert env["APP_ENV"]["value"] == "staging"
        assert env["NO_LIVE_PAYMENT_MODE"]["value"] == "true"
        assert env["KILL_SWITCH_ALL_EXTERNAL_BETA"]["value"] == "true"
        assert env["DATABASE_URL"]["fromDatabase"]["name"] == "graxia-db-staging"
        assert env["CELERY_BROKER_URL"]["fromService"]["name"] == "graxia-redis-staging"
        assert env["CELERY_RESULT_BACKEND"]["fromService"]["name"] == "graxia-redis-staging"


def test_staging_backing_resources_are_distinct():
    config = _render()

    assert {item["name"] for item in config["databases"]} >= {
        "graxia-db",
        "graxia-db-staging",
    }
    assert {item["name"] for item in config["redis"]} >= {
        "graxia-redis",
        "graxia-redis-staging",
    }


def test_private_fulfillment_and_checkout_boundaries_are_explicit():
    config = _render()
    production = _env_map(_service(config, "graxia-revenue-os"))
    staging = _env_map(_service(config, "graxia-revenue-os-staging"))

    private_storage_keys = {
        "REVENUE_OS_PRIVATE_STORAGE_ENDPOINT",
        "REVENUE_OS_PRIVATE_STORAGE_BUCKET",
        "REVENUE_OS_PRIVATE_STORAGE_ACCESS_KEY",
        "REVENUE_OS_PRIVATE_STORAGE_SECRET_KEY",
        "REVENUE_OS_PRIVATE_STORAGE_REGION",
    }
    for env in (production, staging):
        for key in private_storage_keys | {
            "REVENUE_OS_DOWNLOAD_SIGNING_SECRET",
            "REVENUE_OS_PUBLIC_BASE_URL",
        }:
            assert env[key]["sync"] is False

    for name in (
        "graxia-worker-default",
        "graxia-worker-critical",
        "graxia-beat",
        "graxia-revenue-os-staging-worker",
        "graxia-revenue-os-staging-beat",
    ):
        env = _env_map(_service(config, name))
        assert env["REVENUE_OS_DOWNLOAD_SIGNING_SECRET"]["sync"] is False
        assert env["REVENUE_OS_PUBLIC_BASE_URL"]["sync"] is False

    assert production["ALLOWED_ORIGINS"]["value"] == "https://graxia-os-funnel.vercel.app"
    assert staging["ALLOWED_ORIGINS"]["value"] == "https://staging.graxia-os-funnel.vercel.app"
