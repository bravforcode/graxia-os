"""
xiarchitect.core.errors — Error types and reporter
"""


class XiArchitectError(Exception):
    """Base exception for xiarchitect"""
    pass


class ScanError(XiArchitectError):
    """Error during workspace scanning"""
    pass


class AnalysisError(XiArchitectError):
    """Error during file analysis"""
    pass


class GraphBuildError(XiArchitectError):
    """Error during graph construction"""
    pass


class ExportError(XiArchitectError):
    """Error during export"""
    pass


class ConfigurationError(XiArchitectError):
    """Error in configuration"""
    pass


class SecurityError(XiArchitectError):
    """Security-related error"""
    pass
