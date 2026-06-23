"""Execution feature gate. Default: OFF."""
_feature_enabled = False

def is_execution_enabled() -> bool:
    return _feature_enabled

def enable_execution() -> None:
    global _feature_enabled
    _feature_enabled = True

def disable_execution() -> None:
    global _feature_enabled
    _feature_enabled = False
