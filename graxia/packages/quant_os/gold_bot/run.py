"""
Gold Bot - Main Entry Point

AI Trading Bot for XAUUSD (Gold)
13 Strategies | Claude AI Validation | MT5 Execution

Usage:
    cd "graxia os"
    python graxia/packages/quant_os/gold_bot/run.py
"""

import sys
import os
import asyncio

# Add graxia os root to path
sys.path.insert(0, os.getcwd())


async def main():
    """Main entry point"""
    from graxia.packages.quant_os.gold_bot.core.engine import GoldBotEngine
    from graxia.packages.quant_os.gold_bot.core.config import BotConfig
    
    # Configure
    config = BotConfig(
        symbol="XAUUSD",
        primary_timeframe="M15",
        cycle_interval_seconds=30,
        min_score_to_trade=300,
        ai_validation_enabled=True,
        max_risk_per_trade_pct=1.0,
    )
    
    # Create and run bot
    bot = GoldBotEngine(config)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
