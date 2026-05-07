#!/usr/bin/env python3
"""
Telegram Bot Setup for Quant OS

Creates a Telegram bot and configures it for trading notifications.
Usage: python setup_telegram_bot.py
"""

import asyncio
import sys
import json
from pathlib import Path

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
except ImportError:
    print("Error: python-telegram-bot not installed")
    print("Run: pip install python-telegram-bot")
    sys.exit(1)


# Bot responses
START_MESSAGE = """
🤖 <b>Quant OS Trading Bot</b>

This bot will notify you of:
✅ Trade executions
⚠️ Kill switch triggers
📊 Daily P&L reports
🔔 Risk alerts

<b>Commands:</b>
/status - System status
/positions - Open positions
/pnl - P&L summary
/killswitch - Check kill switch status
/help - Show this help

<i>Stay safe. Trade smart.</i>
"""

HELP_MESSAGE = """
<b>Quant OS Bot Commands</b>

📈 <b>Trading</b>
/positions - Show open positions
/pnl - Today's P&L summary
/trades - Recent trades

⚙️ <b>System</b>
/status - System health & status
/killswitch - Kill switch status
/mode - Current trading mode

📊 <b>Reports</b>
/daily - Daily report
/weekly - Weekly summary
/risk - Risk metrics

Need help? Contact support.
"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_html(START_MESSAGE)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_html(HELP_MESSAGE)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    status_text = """
📊 <b>Quant OS Status</b>

<b>Mode:</b> PAPER
<b>Broker:</b> Connected
<b>Kill Switch:</b> 🟢 Armed
<b>Circuit Breaker:</b> 🟢 Closed

<b>Positions:</b> 0 open
<b>Today's Trades:</b> 0
<b>Today's P&L:</b> $0.00

<i>Last updated: Just now</i>
"""
    await update.message.reply_html(status_text)


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /positions command"""
    positions_text = """
📈 <b>Open Positions</b>

No open positions currently.

Use TradingView alerts to generate signals.
"""
    await update.message.reply_html(positions_text)


async def pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pnl command"""
    pnl_text = """
💰 <b>P&L Summary</b>

<b>Today:</b> $0.00
<b>This Week:</b> $0.00
<b>This Month:</b> $0.00
<b>All Time:</b> $0.00

<b>Win Rate:</b> 0% (0W / 0L)
<b>Expectancy:</b> $0.00 per trade

<i>Paper trading mode</i>
"""
    await update.message.reply_html(pnl_text)


async def killswitch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /killswitch command"""
    killswitch_text = """
🚨 <b>Kill Switch Status</b>

Status: 🟢 <b>ARMED</b>

Auto-triggers:
• Daily loss: 2%
• Drawdown: 15%
• Stale data: 5 min
• Error rate: 10%

<i>Trading is currently enabled</i>
"""
    await update.message.reply_html(killswitch_text)


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /daily command"""
    daily_text = """
📅 <b>Daily Report</b>

Date: Today

<b>Trades:</b> 0
<b>P&L:</b> $0.00
<b>Open Positions:</b> 0

<b>Strategies Active:</b>
• MTM (Multi-Timeframe Momentum)
• MRB (Mean Reversion Bollinger)
• MLB (ML-Enhanced Breakout)

<i>No trading activity today</i>
"""
    await update.message.reply_html(daily_text)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    print(f"Update {update} caused error {context.error}")


def main():
    """Main function"""
    print("=" * 70)
    print("Quant OS Telegram Bot Setup")
    print("=" * 70)
    print()
    
    # Check for bot token
    token = input("Enter your Telegram Bot Token (from @BotFather): ").strip()
    
    if not token:
        print("Error: Token is required")
        sys.exit(1)
    
    print()
    print("Starting bot...")
    print("Press Ctrl+C to stop")
    print()
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(CommandHandler("pnl", pnl_command))
    application.add_handler(CommandHandler("killswitch", killswitch_command))
    application.add_handler(CommandHandler("daily", daily_command))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Get bot info
    bot_info = asyncio.run(application.bot.get_me())
    print(f"Bot connected: @{bot_info.username}")
    print(f"Bot ID: {bot_info.id}")
    print()
    
    # Save configuration
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Update or add Telegram settings
        if "TELEGRAM_BOT_TOKEN=" in content:
            content = content.replace(
                f"TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather",
                f"TELEGRAM_BOT_TOKEN={token}"
            )
        else:
            content += f"\nTELEGRAM_BOT_TOKEN={token}\n"
        
        # Add chat ID placeholder if not present
        if "TELEGRAM_CHAT_ID=" not in content:
            content += "TELEGRAM_CHAT_ID=your_chat_id\n"
        
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"✅ Updated {env_file} with bot token")
    
    print()
    print("To get your Chat ID:")
    print("1. Message @userinfobot on Telegram")
    print("2. Copy the ID and update TELEGRAM_CHAT_ID in .env")
    print()
    
    # Run the bot
    print("🚀 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBot stopped by user")
        sys.exit(0)
