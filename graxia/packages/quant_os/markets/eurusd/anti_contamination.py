from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ContaminationCheck:
    name: str
    passed: bool
    evidence: str

@dataclass
class ContaminationReport:
    checks: list[ContaminationCheck] = field(default_factory=list)
    
    @property
    def clean(self) -> bool:
        return all(c.passed for c in self.checks)
    
    def add_check(self, name: str, passed: bool, evidence: str) -> None:
        self.checks.append(ContaminationCheck(name=name, passed=passed, evidence=evidence))

class AntiContaminationGuard:
    """Prevent XAUUSD parameters from contaminating EURUSD research."""
    
    FORBIDDEN_PATTERNS = [
        "xauusd", "gold", "xau",
        "liquidity_sweep",
        "atr_14",
        "2350",
        "2400",
    ]
    
    def check_parameter_source(self, params: dict, source_market: Optional[str] = None) -> ContaminationReport:
        report = ContaminationReport()
        
        if source_market and source_market.upper() in ("XAUUSD", "XAU", "GOLD"):
            report.add_check("PARAMETER_SOURCE", False, f"Parameters from {source_market}")
        else:
            report.add_check("PARAMETER_SOURCE", True, "Parameters not from XAUUSD")
        
        for key, value in params.items():
            key_lower = key.lower()
            for pattern in self.FORBIDDEN_PATTERNS:
                if pattern in key_lower:
                    report.add_check(f"PARAM_NAME:{key}", False, f"Contains '{pattern}'")
                    break
        
        for key, value in params.items():
            if isinstance(value, (int, float)):
                if 2000 < value < 3000:
                    report.add_check(f"PARAM_VALUE:{key}", False, f"Value {value} in gold range")
        
        if not report.checks:
            report.add_check("NO_PARAMS", True, "No parameters to check")
        
        return report
    
    def check_file_content(self, content: str, filename: str = "") -> ContaminationReport:
        report = ContaminationReport()
        content_lower = content.lower()
        
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in content_lower:
                report.add_check(f"CONTENT:{pattern}", False, f"Found '{pattern}' in {filename}")
            else:
                report.add_check(f"CONTENT:{pattern}", True, f"No '{pattern}' in {filename}")
        
        return report
    
    def check_strategy_hash(self, strategy_hash: str, known_xau_hashes: list[str]) -> ContaminationReport:
        report = ContaminationReport()
        
        if strategy_hash in known_xau_hashes:
            report.add_check("STRATEGY_HASH", False, f"Hash {strategy_hash[:16]} matches XAUUSD strategy")
        else:
            report.add_check("STRATEGY_HASH", True, "Hash does not match XAUUSD strategies")
        
        return report
