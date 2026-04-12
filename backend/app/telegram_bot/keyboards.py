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
            buttons.append([
                InlineKeyboardButton("✅ Approve Batch", callback_data=f"approvalbatch:approve:{batch_key}"),
                InlineKeyboardButton("❌ Reject Batch", callback_data=f"approvalbatch:reject:{batch_key}"),
            ])
        return InlineKeyboardMarkup(buttons)
    except ImportError:
        return None
