import json
from pathlib import Path

import pytest

from scripts.repository_inventory import InventoryError, load_inventory, validate_inventory


ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "docs" / "repository-inventory.yaml"


def test_inventory_covers_all_audited_repositories():
    data = load_inventory(INVENTORY)

    assert len(data["repositories"]) == 31
    assert validate_inventory(data) is data
    assert data["audit"]["external_writes"] is False


def test_protected_repositories_cannot_be_cleanup_targets():
    data = load_inventory(INVENTORY)
    protected = {
        item["name"]: item
        for item in data["repositories"]
        if item.get("protected")
    }

    assert set(protected) == {"krisphy", "adminmate-ai"}
    assert all(item["action"] == "keep-active" for item in protected.values())

    changed = json.loads(json.dumps(data))
    changed["repositories"][0]["protected"] = True
    changed["repositories"][0]["action"] = "archive"
    with pytest.raises(InventoryError, match="protected"):
        validate_inventory(changed)


def test_inventory_rejects_duplicate_repository_names():
    data = load_inventory(INVENTORY)
    changed = json.loads(json.dumps(data))
    changed["repositories"].append(changed["repositories"][0])

    with pytest.raises(InventoryError, match="duplicate"):
        validate_inventory(changed)
