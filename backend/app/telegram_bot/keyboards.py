import base64
import hashlib


def approval_batch_callback_ref(batch_key: str) -> str:
    if not isinstance(batch_key, str) or not batch_key:
        raise ValueError("approval_batch_key_invalid")
    digest = hashlib.sha256(batch_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def is_approval_batch_callback_ref(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 43
        and value.isascii()
        and all(char.isalnum() or char in "-_" for char in value)
    )


def opportunity_keyboard(opp_id: str, review_after: str | None = None):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = [
            [
                InlineKeyboardButton("✅ ทำเลย", callback_data=f"opp:approve:{opp_id}"),
                InlineKeyboardButton("❌ ข้าม", callback_data=f"opp:skip:{opp_id}"),
            ]
        ]
        if review_after:
            buttons[0].insert(1, InlineKeyboardButton(f"⏰ เลื่อน ({review_after})", callback_data=f"opp:delay:{opp_id}"))
        return InlineKeyboardMarkup(buttons)
    except ImportError:
        return None


def draft_keyboard(draft_id: str):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"draft:approve:{draft_id}"),
            InlineKeyboardButton("✏️ Revise", callback_data=f"draft:revise:{draft_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"draft:reject:{draft_id}"),
        ]])
    except ImportError:
        return None


def approval_keyboard(approval_id: str, batch_key: str | None = None):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approval:approve:{approval_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"approval:reject:{approval_id}"),
        ]]
        if batch_key:
            callback_ref = approval_batch_callback_ref(batch_key)
            buttons.append([
                InlineKeyboardButton("✅ Approve Batch", callback_data=f"approvalbatch:a:{callback_ref}"),
                InlineKeyboardButton("❌ Reject Batch", callback_data=f"approvalbatch:r:{callback_ref}"),
            ])
        return InlineKeyboardMarkup(buttons)
    except ImportError:
        return None
