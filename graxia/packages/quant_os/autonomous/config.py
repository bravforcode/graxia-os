"""Autonomous trading loop configuration.

Environment-driven settings for the 24/7 LLM trading loop.
"""

import os

# ── Symbols & Timeframes ──────────────────────────────────────────
SYMBOLS: list[str] = [s.strip() for s in os.getenv("AUTO_SYMBOLS", "XAUUSD,BTCUSD,ETHUSD").split(",") if s.strip()]

TIMEFRAMES: list[str] = [t.strip() for t in os.getenv("AUTO_TIMEFRAMES", "15m,1h,4h").split(",") if t.strip()]

# ── Loop Timing ───────────────────────────────────────────────────
CHART_POLL_SECONDS: int = int(os.getenv("AUTO_CHART_POLL_SECONDS", "60"))
DECISION_COOLDOWN_SECONDS: int = int(os.getenv("AUTO_DECISION_COOLDOWN", "300"))
HEALTH_CHECK_SECONDS: int = int(os.getenv("AUTO_HEALTH_CHECK_SECONDS", "30"))

# ── LLM Settings ─────────────────────────────────────────────────
LLM_ANALYSIS_TIMEOUT: float = float(os.getenv("AUTO_LLM_TIMEOUT", "30.0"))
LLM_MIN_CONFIDENCE: float = float(os.getenv("AUTO_LLM_MIN_CONFIDENCE", "0.65"))
LLM_USE_SCREENSHOT: bool = os.getenv("AUTO_LLM_USE_SCREENSHOT", "true").lower() == "true"

# ── Risk Limits ───────────────────────────────────────────────────
MAX_OPEN_POSITIONS: int = int(os.getenv("AUTO_MAX_POSITIONS", "3"))
MAX_DAILY_TRADES: int = int(os.getenv("AUTO_MAX_DAILY_TRADES", "10"))
MAX_DAILY_LOSS_PCT: float = float(os.getenv("AUTO_MAX_DAILY_LOSS_PCT", "3.0"))

# ── Mode ──────────────────────────────────────────────────────────
# paper = LLM can execute directly
# live  = LLM suggests only, human approval required
TRADING_MODE: str = os.getenv("AUTO_TRADING_MODE", "paper")

# ── TradingView CDP ──────────────────────────────────────────────
TV_CDP_ENABLED: bool = os.getenv("AUTO_TV_CDP_ENABLED", "true").lower() == "true"
TV_SCREENSHOT_DIR: str = os.getenv(
    "AUTO_TV_SCREENSHOT_DIR",
    "artifacts/autonomous_screenshots",
)

# ── LLM Rate Limits (daily, with 10% buffer) ─────────────────────
RATE_LIMIT_GROQ_DAILY: int = int(os.getenv("AUTO_RATE_GROQ_DAILY", "900"))
RATE_LIMIT_CEREBRAS_DAILY: int = int(os.getenv("AUTO_RATE_CEREBRAS_DAILY", "13000"))
RATE_LIMIT_OPENROUTER_DAILY: int = int(os.getenv("AUTO_RATE_OPENROUTER_DAILY", "45"))

# ── Health ────────────────────────────────────────────────────────
MAX_CONSECUTIVE_ERRORS: int = int(os.getenv("AUTO_MAX_CONSECUTIVE_ERRORS", "5"))
RESTART_DELAY_SECONDS: int = int(os.getenv("AUTO_RESTART_DELAY", "60"))
