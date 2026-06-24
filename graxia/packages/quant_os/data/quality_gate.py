"""
Data Quality Gate for Quant OS

Validates data before it's used in trading decisions.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass

from ..core.enums import DataQualityCheck


@dataclass
class QualityCheckResult:
    """Result of a data quality check"""
    check_name: DataQualityCheck
    passed: bool
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class DataQualityGate:
    """
    Data Quality Gate
    
    Validates data integrity before trading:
    - Missing timestamps
    - Duplicate timestamps
    - Outlier prices
    - Stale quotes
    - Zero volume
    """
    
    def __init__(self):
        self.thresholds = {
            "max_price_spike_pct": 5.0,      # Max 5% price spike
            "max_staleness_seconds": 60,    # Max 60 second staleness
            "min_volume_threshold": 1,       # Minimum volume
        }
    
    def validate_ohlcv(self, data: List[Dict]) -> List[QualityCheckResult]:
        """Validate OHLCV data series"""
        results = []
        
        # Check for missing timestamps
        results.append(self._check_missing_timestamps(data))
        
        # Check for duplicate timestamps
        results.append(self._check_duplicate_timestamps(data))
        
        # Check for outlier prices
        results.append(self._check_outlier_prices(data))
        
        # Check for zero volume
        results.append(self._check_zero_volume(data))
        
        # Check for stale quotes
        results.append(self._check_stale_quotes(data))
        
        return results
    
    def _check_missing_timestamps(self, data: List[Dict]) -> QualityCheckResult:
        """Check for missing timestamps"""
        missing = [d for d in data if not d.get("timestamp")]
        return QualityCheckResult(
            check_name=DataQualityCheck.MISSING_TIMESTAMP,
            passed=len(missing) == 0,
            details={"missing_count": len(missing)}
        )
    
    def _check_duplicate_timestamps(self, data: List[Dict]) -> QualityCheckResult:
        """Check for duplicate timestamps"""
        timestamps = [d.get("timestamp") for d in data if d.get("timestamp")]
        duplicates = len(timestamps) - len(set(timestamps))
        return QualityCheckResult(
            check_name=DataQualityCheck.DUPLICATE_TIMESTAMP,
            passed=duplicates == 0,
            details={"duplicate_count": duplicates}
        )
    
    def _check_outlier_prices(self, data: List[Dict]) -> QualityCheckResult:
        """Check for price outliers"""
        if len(data) < 2:
            return QualityCheckResult(
                check_name=DataQualityCheck.OUTLIER_PRICE,
                passed=True
            )
        
        prices = [d.get("close", 0) for d in data if d.get("close")]
        if not prices:
            return QualityCheckResult(
                check_name=DataQualityCheck.OUTLIER_PRICE,
                passed=True
            )
        
        avg_price = sum(prices) / len(prices)
        max_spike = max(abs(p - avg_price) / avg_price * 100 for p in prices) if avg_price > 0 else 0
        
        return QualityCheckResult(
            check_name=DataQualityCheck.OUTLIER_PRICE,
            passed=max_spike < self.thresholds["max_price_spike_pct"],
            details={"max_spike_pct": max_spike, "threshold": self.thresholds["max_price_spike_pct"]}
        )
    
    def _check_zero_volume(self, data: List[Dict]) -> QualityCheckResult:
        """Check for zero volume bars"""
        zero_vol = [d for d in data if d.get("volume", 0) == 0]
        return QualityCheckResult(
            check_name=DataQualityCheck.ZERO_VOLUME,
            passed=len(zero_vol) == 0 or len(zero_vol) < len(data) * 0.1,  # Allow up to 10%
            details={"zero_volume_count": len(zero_vol)}
        )
    
    def _check_stale_quotes(self, data: List[Dict]) -> QualityCheckResult:
        """Check for stale quotes"""
        if not data:
            return QualityCheckResult(
                check_name=DataQualityCheck.STALE_QUOTE,
                passed=True
            )
        
        latest = data[-1]
        latest_ts = latest.get("timestamp")
        
        if isinstance(latest_ts, datetime):
            age_seconds = (datetime.now(timezone.utc) - latest_ts).total_seconds()
            return QualityCheckResult(
                check_name=DataQualityCheck.STALE_QUOTE,
                passed=age_seconds < self.thresholds["max_staleness_seconds"],
                details={"staleness_seconds": age_seconds}
            )
        
        return QualityCheckResult(
            check_name=DataQualityCheck.STALE_QUOTE,
            passed=True
        )
    
    def all_checks_passed(self, results: List[QualityCheckResult]) -> bool:
        """Check if all quality checks passed"""
        return all(r.passed for r in results)
