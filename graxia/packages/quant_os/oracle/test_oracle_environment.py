"""Tests for oracle environment isolation."""
import tempfile
from graxia.packages.quant_os.oracle.oracle_environment import (
    OracleEnvironment, OracleEnvironmentManager
)


def test_environment_valid():
    env = OracleEnvironment(
        name="canonical", python_version="3.12", framework_version="1.0",
        adapter_version="0.1", license_decision="MIT",
    )
    ok, issues = env.validate()
    assert ok


def test_environment_rejects_credentials():
    env = OracleEnvironment(
        name="bad", python_version="3.12", framework_version="1.0",
        adapter_version="0.1", license_decision="MIT",
        has_broker_credentials=True,
    )
    ok, issues = env.validate()
    assert not ok
    assert any("credentials" in i for i in issues)


def test_manager_register_and_list():
    mgr = OracleEnvironmentManager()
    env = OracleEnvironment(
        name="vectorbt", python_version="3.12", framework_version="0.4",
        adapter_version="0.1", license_decision="Apache-2.0",
    )
    mgr.register(env)
    assert "vectorbt" in mgr.list_all()


def test_manager_validate_all():
    mgr = OracleEnvironmentManager()
    mgr.register(OracleEnvironment(
        name="good", python_version="3.12", framework_version="1.0",
        adapter_version="0.1", license_decision="MIT",
    ))
    mgr.register(OracleEnvironment(
        name="bad", python_version="3.12", framework_version="1.0",
        adapter_version="0.1", license_decision="MIT",
        has_broker_credentials=True,
    ))
    results = mgr.validate_all()
    assert results["good"][0] is True
    assert results["bad"][0] is False


def test_manager_ensure_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = OracleEnvironmentManager(tmp)
        mgr.register(OracleEnvironment(
            name="test_env", python_version="3.12", framework_version="1.0",
            adapter_version="0.1", license_decision="MIT",
        ))
        dirs = mgr.ensure_dirs()
        assert len(dirs) == 1
