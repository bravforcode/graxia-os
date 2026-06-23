"""Global kill switch. Default: ON (blocked)."""
_kill_switch_active = True

def is_kill_switch_active() -> bool:
    return _kill_switch_active

def activate_kill_switch() -> None:
    global _kill_switch_active
    _kill_switch_active = True

def release_kill_switch() -> None:
    global _kill_switch_active
    _kill_switch_active = False
