import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    """
    Sends a message to the CEO via Telegram.
    Uses the requests library for a simple synchronous call.
    """
    if not TOKEN or not CHAT_ID:
        print(f"[Notification Stub] Telegram not configured. Message: {message}")
        return False
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return True
        else:
            print(f"Error sending Telegram message: {response.text}")
            return False
    except Exception as e:
        print(f"Exception sending Telegram message: {e}")
        return False

async def send_telegram_message_async(message: str):
    """
    Async version of the notification helper.
    """
    # For now, just wrap the sync one to keep it simple
    return send_telegram_message(message)
