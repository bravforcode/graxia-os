"""Core module - golden rules, enums, config, exceptions

Lazy imports to avoid triggering the full dependency chain (golden_rules → risk)
when lightweight modules like core.tv_integration are imported directly.
"""


def __getattr__(name: str):
    """Lazy-load core attributes so that submodules can be imported
    without pulling in the entire dependency tree."""
    _lazy = {
        # golden_rules
        "GOLDEN_RULES": (".golden_rules", "GOLDEN_RULES"),
        # enums
        "SystemState": (".enums", "SystemState"),
        "TradingMode": (".enums", "TradingMode"),
        "OrderStatus": (".enums", "OrderStatus"),
        "OrderSide": (".enums", "OrderSide"),
        "OrderType": (".enums", "OrderType"),
        "TimeInForce": (".enums", "TimeInForce"),
        "RegimeType": (".enums", "RegimeType"),
        "KillSwitchType": (".enums", "KillSwitchType"),
        "IncidentSeverity": (".enums", "IncidentSeverity"),
        "StrategyStatus": (".enums", "StrategyStatus"),
        "ModelStatus": (".enums", "ModelStatus"),
        "DataSourceTier": (".enums", "DataSourceTier"),
        "SignalType": (".enums", "SignalType"),
        "DecisionType": (".enums", "DecisionType"),
        # config
        "QuantConfig": (".config", "QuantConfig"),
        "get_config": (".config", "get_config"),
        # exceptions
        "QuantException": (".exceptions", "QuantException"),
        "RiskViolationError": (".exceptions", "RiskViolationError"),
        "ComplianceError": (".exceptions", "ComplianceError"),
        "KillSwitchTriggeredError": (".exceptions", "KillSwitchTriggeredError"),
        "DataQualityError": (".exceptions", "DataQualityError"),
        "BrokerError": (".exceptions", "BrokerError"),
        "OverfittingError": (".exceptions", "OverfittingError"),
        "InsufficientEvidenceError": (".exceptions", "InsufficientEvidenceError"),
    }
    if name in _lazy:
        module_path, attr = _lazy[name]
        import importlib

        mod = importlib.import_module(module_path, package=__name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "GOLDEN_RULES",
    "SystemState",
    "TradingMode",
    "OrderStatus",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "RegimeType",
    "KillSwitchType",
    "IncidentSeverity",
    "StrategyStatus",
    "ModelStatus",
    "DataSourceTier",
    "SignalType",
    "DecisionType",
    "QuantConfig",
    "get_config",
    "QuantException",
    "RiskViolationError",
    "ComplianceError",
    "KillSwitchTriggeredError",
    "DataQualityError",
    "BrokerError",
    "OverfittingError",
    "InsufficientEvidenceError",
]
