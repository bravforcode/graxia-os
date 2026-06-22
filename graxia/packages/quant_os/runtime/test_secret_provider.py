"""Tests for secret_provider."""
import os
import tempfile
from pathlib import Path

from .secret_provider import SecretProvider, SecretRef


def test_secret_provider_env(monkeypatch):
    monkeypatch.setenv("TEST_SECRET_KEY", "s3cret")
    provider = SecretProvider()
    provider.add_reference("api_key", SecretRef(name="api_key", source="env", env_var="TEST_SECRET_KEY"))
    assert provider.get_secret("api_key") == "s3cret"


def test_secret_provider_missing():
    provider = SecretProvider()
    try:
        provider.get_secret("nonexistent")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not configured" in str(e)


def test_secret_provider_repr_no_leak(monkeypatch):
    monkeypatch.setenv("LEAK_SECRET", "topsecret")
    provider = SecretProvider()
    provider.add_reference("key", SecretRef(name="key", source="env", env_var="LEAK_SECRET"))
    provider.get_secret("key")
    r = repr(provider)
    s = str(provider)
    assert "topsecret" not in r
    assert "topsecret" not in s


def test_secret_provider_cache(monkeypatch):
    monkeypatch.setenv("CACHED_SECRET", "cached_val")
    provider = SecretProvider()
    ref = SecretRef(name="cached", source="env", env_var="CACHED_SECRET")
    provider.add_reference("cached", ref)
    first = provider.get_secret("cached")
    # mutate env to prove cache wins
    monkeypatch.setenv("CACHED_SECRET", "changed")
    second = provider.get_secret("cached")
    assert first == second == "cached_val"


def test_secret_provider_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("file_secret_value\n")
        path = f.name
    try:
        provider = SecretProvider()
        provider.add_reference("file_key", SecretRef(name="file_key", source="file", file_path=path))
        assert provider.get_secret("file_key") == "file_secret_value"
    finally:
        os.unlink(path)


def test_secret_provider_unknown_source():
    provider = SecretProvider()
    provider.add_reference("bad", SecretRef(name="bad", source="keychain"))
    try:
        provider.get_secret("bad")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown secret source" in str(e)
