"""Custom exceptions for Quant OS"""


class QuantException(Exception):
    """Base exception for all Quant OS errors"""
    def __init__(self, message: str, error_code: str = "QUANT_ERROR", context: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}


class RiskViolationError(QuantException):
    """Raised when a trade violates risk limits"""
    def __init__(self, message: str, violation_type: str = "", context: dict = None):
        super().__init__(message, "RISK_VIOLATION", context)
        self.violation_type = violation_type


class ComplianceError(QuantException):
    """Raised when a trade fails compliance checks"""
    def __init__(self, message: str, compliance_check: str = "", context: dict = None):
        super().__init__(message, "COMPLIANCE_ERROR", context)
        self.compliance_check = compliance_check


class KillSwitchTriggeredError(QuantException):
    """Raised when kill switch is triggered"""
    def __init__(self, message: str, switch_type: str = "", context: dict = None):
        super().__init__(message, "KILL_SWITCH", context)
        self.switch_type = switch_type


class DataQualityError(QuantException):
    """Raised when data quality check fails"""
    def __init__(self, message: str, check_type: str = "", context: dict = None):
        super().__init__(message, "DATA_QUALITY_ERROR", context)
        self.check_type = check_type


class BrokerError(QuantException):
    """Raised when broker API interaction fails"""
    def __init__(self, message: str, broker: str = "", context: dict = None):
        super().__init__(message, "BROKER_ERROR", context)
        self.broker = broker


class OverfittingError(QuantException):
    """Raised when strategy fails anti-overfitting validation"""
    def __init__(self, message: str, test_failed: str = "", context: dict = None):
        super().__init__(message, "OVERFITTING_ERROR", context)
        self.test_failed = test_failed


class InsufficientEvidenceError(QuantException):
    """Raised when strategy lacks sufficient evidence for promotion"""
    def __init__(self, message: str, missing_evidence: list = None, context: dict = None):
        super().__init__(message, "INSUFFICIENT_EVIDENCE", context)
        self.missing_evidence = missing_evidence or []


class OrderStateError(QuantException):
    """Raised when order state transition is invalid"""
    def __init__(self, message: str, from_state: str = "", to_state: str = "", context: dict = None):
        super().__init__(message, "ORDER_STATE_ERROR", context)
        self.from_state = from_state
        self.to_state = to_state


class DuplicateOrderError(QuantException):
    """Raised when duplicate order is detected"""
    def __init__(self, message: str, idempotency_key: str = "", context: dict = None):
        super().__init__(message, "DUPLICATE_ORDER", context)
        self.idempotency_key = idempotency_key


class PositionMismatchError(QuantException):
    """Raised when internal position doesn't match broker"""
    def __init__(self, message: str, symbol: str = "", context: dict = None):
        super().__init__(message, "POSITION_MISMATCH", context)
        self.symbol = symbol


class ValidationError(QuantException):
    """Raised when input validation fails"""
    def __init__(self, message: str, field: str = "", context: dict = None):
        super().__init__(message, "VALIDATION_ERROR", context)
        self.field = field


class StrategyError(QuantException):
    """Raised when strategy execution fails"""
    def __init__(self, message: str, strategy_id: str = "", context: dict = None):
        super().__init__(message, "STRATEGY_ERROR", context)
        self.strategy_id = strategy_id


class MLModelError(QuantException):
    """Raised when ML model inference fails"""
    def __init__(self, message: str, model_id: str = "", context: dict = None):
        super().__init__(message, "ML_MODEL_ERROR", context)
        self.model_id = model_id


class DriftDetectedError(QuantException):
    """Raised when model drift exceeds threshold"""
    def __init__(self, message: str, model_id: str = "", drift_score: float = 0.0, context: dict = None):
        super().__init__(message, "DRIFT_DETECTED", context)
        self.model_id = model_id
        self.drift_score = drift_score


class CircuitBreakerError(QuantException):
    """Raised when circuit breaker trips"""
    def __init__(self, message: str, breaker_type: str = "", context: dict = None):
        super().__init__(message, "CIRCUIT_BREAKER", context)
        self.breaker_type = breaker_type
