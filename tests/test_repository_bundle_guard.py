from pathlib import Path

import pytest

from scripts.repository_bundle_guard import (
    BundleGuardError,
    _parse_heads,
    validate_cleanup_target,
    verify_bundle,
)
from scripts.repository_inventory import load_inventory


ROOT = Path(__file__).parents[1]
INVENTORY = load_inventory(ROOT / "docs" / "repository-inventory.yaml")


def test_protected_repo_is_rejected_before_bundle_access(tmp_path: Path):
    with pytest.raises(BundleGuardError, match="protected"):
        validate_cleanup_target(
            INVENTORY,
            repo_name="krisphy",
            action="archive",
            bundle_path=tmp_path / "does-not-exist.bundle",
        )


def test_cleanup_action_must_match_inventory(tmp_path: Path):
    with pytest.raises(BundleGuardError, match="does not match"):
        validate_cleanup_target(
            INVENTORY,
            repo_name="auto-post",
            action="archive",
            bundle_path=tmp_path / "does-not-exist.bundle",
        )


def test_cleanup_target_requires_restore_bundle(tmp_path: Path):
    with pytest.raises(BundleGuardError, match="bundle is missing"):
        validate_cleanup_target(
            INVENTORY,
            repo_name="auto-post",
            action="merge-then-archive",
            bundle_path=tmp_path / "does-not-exist.bundle",
        )


def test_parse_heads_returns_only_safe_sha_references():
    heads = _parse_heads(
        "a" * 40 + " refs/heads/main\nnot-a-head refs/heads/bad\n" + "b" * 40
    )
    assert heads == ["a" * 40, "b" * 40]


def test_verify_bundle_is_read_only_and_binds_expected_head(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "auto-post.bundle"
    bundle.write_bytes(b"test bundle placeholder")
    expected_head = "a" * 40
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        calls.append(args)
        if args[1] == "list-heads":
            return f"{expected_head} refs/heads/master\n"
        return "verified"

    monkeypatch.setattr("scripts.repository_bundle_guard._run_git", fake_git)
    report = verify_bundle(
        INVENTORY,
        repo_name="auto-post",
        action="merge-then-archive",
        bundle_path=bundle,
        expected_head=expected_head,
    )

    assert report["verified"] is True
    assert report["external_writes"] is False
    assert [call[1] for call in calls] == ["verify", "list-heads"]
