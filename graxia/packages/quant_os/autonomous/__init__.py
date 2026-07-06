"""Autonomous Trading Loop — LLM-driven 24/7 trading system.

Components:
    chart_monitor  — Continuous TradingView chart data collection via CDP/MCP
    decision_engine — LLM analysis of chart data → trade signals
    order_executor  — Signal → risk check → broker execution
    orchestrator    — 24/7 main loop, health monitoring, kill switch
    notifications   — Telegram trade alerts and error notifications
    rate_limiter    — Token-bucket rate limiting for LLM API calls

Safety:
    - Paper mode: LLM can trigger orders directly
    - Live mode: LLM suggests only, human approval required (Golden Rule #2)
    - Kill switch always active, AI_CANNOT_OVERRIDE = True
"""
