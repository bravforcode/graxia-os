import csv
from pathlib import Path


ROOT = Path(__file__).parents[1]
CROSSWALK = ROOT / "docs" / "consolidation" / "auto-post-file-disposition.csv"
ALLOWED = {"port", "adapt", "already-covered", "archive-reference", "reject"}


def test_core_auto_post_crosswalk_is_unique_and_targeted():
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert {"donor_path", "disposition", "target_path", "target_status", "rationale"} <= set(rows[0])
    assert len({row["donor_path"] for row in rows}) == len(rows)
    assert all(row["disposition"] in ALLOWED for row in rows)
    assert all(row["rationale"].strip() for row in rows)
    for row in rows:
        if row["disposition"] in {"port", "adapt"}:
            assert row["target_path"].strip()
            assert row["target_status"] in {"existing", "planned"}


def test_collision_boundaries_are_explicit():
    text = (ROOT / "docs" / "consolidation" / "auto-post-capability-crosswalk.md").read_text(
        encoding="utf-8"
    )

    for term in ("auth", "tenant", "Celery", "dry-run", "idempotency", "14-day"):
        assert term in text
