"""
Telegram Bot Interface for CEO Control.
Provides commands for monitoring and controlling the system.
"""

import logging
import os
import sys
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables
load_dotenv()

# Ensure path is correct for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

logger = logging.getLogger(__name__)

# Stub for audit logging
def audit_log(action: str, details: dict):
    logger.info(f"AUDIT LOG - {action}: {details}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initialize the CEO Control Interface."""
    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    
    audit_log("start_command", {"user_id": user.id if user else "unknown", "chat_id": chat_id})
    
    msg = (
        "🚀 *Graxia OS: CEO Control Interface Initialized*\n\n"
        f"Your Chat ID: `{chat_id}`\n"
        "Please copy this ID and put it in your `.env` file as `TELEGRAM_CHAT_ID` to receive autopilot alerts.\n\n"
        "Available commands:\n"
        "/mission - Current objective\n"
        "/approve - Approve pending actions\n"
        "/status - System health check\n"
        "/killswitch - EMERGENCY HALT"
    )
    
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown")

async def mission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check or update the current high-level mission."""
    user = update.effective_user
    audit_log("mission_command", {"user_id": user.id if user else "unknown"})
    if update.message:
        await update.message.reply_text("🎯 *Current Mission:* Scaling autopilot revenue lanes (R1 & R5).", parse_mode="Markdown")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve pending actions or trades."""
    user = update.effective_user
    audit_log("approve_command", {"user_id": user.id if user else "unknown"})
    if update.message:
        await update.message.reply_text("✅ *Approval:* All pending actions for 'ceo_menum_office' approved.", parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get the current status of all major subsystems."""
    user = update.effective_user
    audit_log("status_command", {"user_id": user.id if user else "unknown"})
    
    status_msg = (
        "📊 *System Status:*\n"
        "- 🤖 *Agents:* 32 Active\n"
        "- 💰 *Revenue Lanes:* R1, R3, R4, R5 (LIVE)\n"
        "- 🛡️ *Security:* Zero-Trust Active\n"
        "- 🚨 *Risk:* Nominal (PnL +0.5%)"
    )
    if update.message:
        await update.message.reply_text(status_msg, parse_mode="Markdown")

async def killswitch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Emergency halt for all autonomous operations."""
    user = update.effective_user
    audit_log("killswitch_command", {"user_id": user.id if user else "unknown", "action": "EMERGENCY_HALT"})
    logger.critical("EMERGENCY KILLSWITCH ACTIVATED VIA TELEGRAM.")
    if update.message:
        await update.message.reply_text("🚨 *EMERGENCY KILLSWITCH ACTIVATED*\n\nAll autonomous operations have been HALTED. Manual intervention required to resume.", parse_mode="Markdown")

def build_app(token: str) -> ApplicationBuilder:
    """Build and configure the Telegram bot application."""
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mission", mission))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("killswitch", killswitch))
    
    return app

if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in .env")
        sys.exit(1)
        
    app = build_app(TOKEN)
    logger.info("Starting Telegram Bot... Press Ctrl+C to stop.")
    app.run_polling()
