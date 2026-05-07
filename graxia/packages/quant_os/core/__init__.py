"""Core module - golden rules, enums, config, exceptions"""
from .golden_rules import GOLDEN_RULES
from .enums import (
    SystemState, TradingMode, OrderStatus, OrderSide, OrderType,
    TimeInForce, RegimeType, KillSwitchType, IncidentSeverity,
    StrategyStatus, ModelStatus, DataSourceTier, SignalType, DecisionType
)
from .config import QuantConfig, get_config
from .exceptions import (
    QuantException, RiskViolationError, ComplianceError,
    KillSwitchTriggeredError, DataQualityError, BrokerError,
    OverfittingError, InsufficientEvidenceError
)

__all__ = [
    "GOLDEN_RULES",
    "SystemState", "TradingMode", "OrderStatus", "OrderSide", "OrderType",
    "TimeInForce", "RegimeType", "KillSwitchType", "IncidentSeverity",
    "StrategyStatus", "ModelStatus", "DataSourceTier", "SignalType", "DecisionType",
    "QuantConfig", "get_config",
    "QuantException", "RiskViolationError", "ComplianceError",
    "KillSwitchTriggeredError", "DataQualityError", "BrokerError",
    "OverfittingError", "InsufficientEvidenceError",
]
