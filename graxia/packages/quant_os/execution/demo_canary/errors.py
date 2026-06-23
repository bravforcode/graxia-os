"""Canary errors."""
class CanaryError(Exception):
    pass
class StateTransitionError(CanaryError):
    pass
class GuardRejectionError(CanaryError):
    pass
class ApprovalError(CanaryError):
    pass
