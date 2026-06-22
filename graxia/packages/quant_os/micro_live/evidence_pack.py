"""
Evidence Pack — assemble all required evidence for micro-live review.

Required evidence per master plan:
- Historical validation pack
- Oracle comparison pack
- Locked holdout result
- Shadow results
- Demo campaign results
- Incident history
- Observed fill/slippage comparison
- Security/SBOM review
- Broker/account contract evidence
- Rollback and kill-switch verification
"""
import os
import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class EvidenceItem:
    name: str
    category: str
    status: str  # "present", "missing", "partial"
    path: Optional[str] = None
    hash_sha256: Optional[str] = None
    details: str = ""


@dataclass
class EvidencePack:
    pack_id: str
    created_at: str
    items: List[EvidenceItem] = field(default_factory=list)
    
    def add_item(self, name: str, category: str, status: str, 
                 path: str = None, details: str = "") -> None:
        item = EvidenceItem(
            name=name, category=category, status=status,
            path=path, details=details,
        )
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                item.hash_sha256 = hashlib.sha256(f.read()).hexdigest()
        self.items.append(item)
    
    def summary(self) -> Dict[str, int]:
        present = sum(1 for i in self.items if i.status == "present")
        missing = sum(1 for i in self.items if i.status == "missing")
        partial = sum(1 for i in self.items if i.status == "partial")
        return {"present": present, "missing": missing, "partial": partial, "total": len(self.items)}
    
    def all_present(self) -> bool:
        return all(i.status == "present" for i in self.items)
    
    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "created_at": self.created_at,
            "summary": self.summary(),
            "items": [{
                "name": i.name,
                "category": i.category,
                "status": i.status,
                "path": i.path,
                "hash": i.hash_sha256,
                "details": i.details,
            } for i in self.items],
        }
    
    def fingerprint(self) -> str:
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


class EvidencePackBuilder:
    """Build evidence pack from project artifacts."""
    
    def __init__(self, project_root: str = "."):
        self._root = project_root
    
    def build(self) -> EvidencePack:
        pack = EvidencePack(
            pack_id=f"ep_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.utcnow().isoformat(),
        )
        
        # 1. Historical validation pack
        pack.add_item(
            "Historical Backtest Results",
            "validation",
            self._check_file("reports/REPORT_PHASE_3_1_ENGINE_INTEGRATION.md"),
            "reports/REPORT_PHASE_3_1_ENGINE_INTEGRATION.md",
        )
        
        # 2. Locked holdout result
        pack.add_item(
            "Locked XAUUSD Revalidation",
            "validation",
            self._check_file("reports/REPORT_PHASE_3B.md"),
            "reports/REPORT_PHASE_3B.md",
        )
        
        # 3. Shadow results
        shadow_files = self._list_files("shadow_results", "*.json")
        pack.add_item(
            "Shadow Session Data",
            "shadow",
            "present" if shadow_files else "missing",
            details=f"{len(shadow_files)} shadow files found",
        )
        
        # 4. Demo campaign results
        campaign_files = self._list_files("shadow_results", "campaign_*.json")
        pack.add_item(
            "Demo Campaign Results",
            "campaign",
            "present" if campaign_files else "missing",
            details=f"{len(campaign_files)} campaign files found",
        )
        
        # 5. Incident drills
        drill_files = self._list_files("shadow_results", "drills_*.json")
        pack.add_item(
            "Incident Drill Results",
            "drills",
            "present" if drill_files else "missing",
            details=f"{len(drill_files)} drill files found",
        )
        
        # 6. Kill switch verification
        pack.add_item(
            "Kill Switch Code",
            "safety",
            self._check_file("canary/config.py"),
            "canary/config.py",
            "execution_enabled=False default",
        )
        
        # 7. Risk policy
        pack.add_item(
            "Risk Policy Version",
            "risk",
            self._check_file("core/config.py"),
            "core/config.py",
        )
        
        # 8. Broker contract
        pack.add_item(
            "Broker Profile",
            "broker",
            self._check_file("mt5_connector/config.yaml"),
            "mt5_connector/config.yaml",
        )
        
        # 9. SBOM
        pack.add_item(
            "Supply Chain SBOM",
            "security",
            self._check_file("repo_intelligence/supply_chain.py"),
            "repo_intelligence/supply_chain.py",
        )
        
        # 10. Compliance matrix
        pack.add_item(
            "Master Plan Compliance Matrix",
            "governance",
            self._check_file("reports/COMPLIANCE_MATRIX.md"),
            "reports/COMPLIANCE_MATRIX.md",
        )
        
        return pack
    
    def _check_file(self, rel_path: str) -> str:
        full = os.path.join(self._root, rel_path)
        return "present" if os.path.exists(full) else "missing"
    
    def _list_files(self, rel_dir: str, pattern: str) -> List[str]:
        full_dir = os.path.join(self._root, rel_dir)
        if not os.path.exists(full_dir):
            return []
        import glob
        return glob.glob(os.path.join(full_dir, pattern))
