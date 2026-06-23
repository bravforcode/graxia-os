"""Single-process execution mutex."""
import threading

_mutex = threading.Lock()
_mutex_held = False

def acquire_mutex() -> bool:
    global _mutex_held
    with _mutex:
        if _mutex_held:
            return False
        _mutex_held = True
        return True

def release_mutex() -> None:
    global _mutex_held
    with _mutex:
        _mutex_held = False

def is_mutex_held() -> bool:
    global _mutex_held
    return _mutex_held
