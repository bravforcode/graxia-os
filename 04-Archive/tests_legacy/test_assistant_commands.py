from app.core.assistant_commands import parse_command_text, render_help_text


def test_parse_command_text_handles_telegram_bot_suffix_and_args():
    parsed = parse_command_text("/status@personal_os_bot now")

    assert parsed.command == "status"
    assert parsed.args == ["now"]


def test_parse_command_text_accepts_plain_text_shortcuts():
    parsed = parse_command_text("today")

    assert parsed.command == "today"
    assert parsed.args == []


def test_render_help_text_lists_core_commands():
    help_text = render_help_text()

    assert "/status" in help_text
    assert "/today" in help_text
    assert "/approvals" in help_text
    assert "/jobs" in help_text
