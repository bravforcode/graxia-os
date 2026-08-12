"""
Gold Bot - AI Trading Bot for XAUUSD (Gold)

13 strategies running in parallel, scored 0-100%, executed via MT5.
Claude AI validates signals before execution.

Architecture:
    Signal Engine → Scoring → Claude AI Validator → Risk Check → MT5 Execution
"""

__version__ = "1.0.0"
__symbol__ = "XAUUSD"
