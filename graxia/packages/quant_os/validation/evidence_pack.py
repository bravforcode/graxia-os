"""Phase BE-P11 — Evidence pack assembler."""
from dataclasses import dataclass
import json


@dataclass
class EvidenceItem:
    item_id: str
    category: str  # historical, oracle, shadow, demo, incident, cost, risk, contract, release
    description: str
    status: str = "present"  # present, missing, incomplete
    artifact_path: str = ""
    hash: str = ""
    notes: str = ""


class EvidencePack:
    """Assemble evidence for promotion review."""
    
    REQUIRED_ITEMS = [
        ("historical_validation", "historical", "Real locked historical validation results"),
        ("oracle_comparison", "oracle", "Independent oracle comparison report"),
        ("shadow_report", "shadow", "Shadow campaign report"),
        ("demo_report", "demo", "Demo campaign report"),
        ("incident_register", "incident", "Incident register with root-cause status"),
        ("cost_calibration", "cost", "Cost-model calibration report"),
        ("risk_adherence", "risk", "Risk adherence report"),
        ("contract_evidence", "contract", "Contract/profile evidence"),
        ("release_bundle", "release", "Release bundle with hashes"),
    ]
    
    def __init__(self):
        self._items: list[EvidenceItem] = []
    
    def build(self, evidence: dict) -> list[EvidenceItem]:
        """Build evidence pack from provided data."""
        self._items = []
        for item_id, category, description in self.REQUIRED_ITEMS:
            if item_id in evidence:
                item = EvidenceItem(
                    item_id=item_id,
                    category=category,
                    description=description,
                    status="present",
                )
                if isinstance(evidence[item_id], dict):
                    item.notes = json.dumps(evidence[item_id], default=str)[:200]
            else:
                item = EvidenceItem(
                    item_id=item_id,
                    category=category,
                    description=description,
                    status="missing",
                )
            self._items.append(item)
        return self._items
    
    def is_complete(self) -> bool:
        return all(i.status == "present" for i in self._items)
    
    def get_missing(self) -> list[EvidenceItem]:
        return [i for i in self._items if i.status != "present"]
    
    def summary(self) -> dict:
        present = sum(1 for i in self._items if i.status == "present")
        return {
            "total": len(self._items),
            "present": present,
            "missing": len(self._items) - present,
            "complete": self.is_complete(),
        }
    
    def to_report(self) -> str:
        lines = ["# Evidence Pack\n"]
        for item in self._items:
            status = "[OK]" if item.status == "present" else "[MISSING]"
            lines.append(f"- {status} {item.description}")
        lines.append(f"\nComplete: {self.is_complete()}")
        return "\n".join(lines)
