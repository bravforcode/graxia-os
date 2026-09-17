from pathlib import Path


ROOT = Path(__file__).parents[1]
MAP = ROOT / "docs" / "consolidation" / "revenue-os-delta-map.md"


def test_delta_map_is_explicitly_non_production_and_source_pinned():
    text = MAP.read_text(encoding="utf-8")

    assert "39eb5116e38cbba19db577d945218edb369ffe3f" in text
    assert "PARITY_EXECUTION_PENDING" in text
    for term in ("signature", "idempotency", "migration", "same image digest", "archive-ready"):
        assert term in text


def test_delta_map_rejects_duplicate_runtime_owners():
    text = MAP.read_text(encoding="utf-8")

    assert "reject` duplicate shims" in text
    assert "reject` donor IDs" in text
    assert "reject` second app" in text
