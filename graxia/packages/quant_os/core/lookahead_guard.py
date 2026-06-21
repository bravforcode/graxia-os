"""Zero look-ahead guard from Jesse pattern"""
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class LookaheadViolation(Exception):
    """Raised when lookahead bias is detected in strict mode"""
    pass

class LookaheadGuard:
    """Enforces zero look-ahead bias in backtesting"""
    
    def __init__(self, strict: bool = False):
        self._current_index: int = 0
        self._data_length: int = 0
        self._violations: List[str] = []
        self._strict = strict
    
    def initialize(self, data_length: int):
        """Initialize with data length"""
        self._data_length = data_length
        self._current_index = 0
        self._violations = []
    
    def advance(self):
        """Advance to next bar"""
        if self._current_index < self._data_length:
            self._current_index += 1
    
    def check_data_access(self, requested_index: int, caller: str = "") -> bool:
        """Check if data access is valid (no future data)"""
        if requested_index > self._current_index:
            msg = f"LOOKAHEAD VIOLATION: {caller} accessed index {requested_index} but current is {self._current_index}"
            self._violations.append(msg)
            if self._strict:
                raise LookaheadViolation(msg)
            logger.error(msg)
            return False
        return True
    
    def get_slice(self, data: Dict[str, List], end_index: Optional[int] = None) -> Dict[str, List]:
        """Get data slice up to and including current index (no future data)"""
        idx = end_index if end_index is not None else self._current_index
        return {k: v[:idx+1] for k, v in data.items()}
    
    @property
    def violations(self) -> List[str]:
        return self._violations
    
    @property
    def has_violations(self) -> bool:
        return len(self._violations) > 0
    
    def reset(self):
        self._current_index = 0
        self._violations = []
