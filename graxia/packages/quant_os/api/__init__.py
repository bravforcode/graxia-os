"""API module - FastAPI routers for Quant OS

Lazy imports to avoid pulling in heavy dependencies at package level.
New modules (tv_client, tv_cdp, visual_routes) don't need the full API stack.
"""


def __getattr__(name: str):
    """Lazy-load routers so that lightweight modules (tv_client, etc.) can be
    imported without triggering the entire dependency chain."""
    _lazy = {
        "webhook_router": (".webhook", "webhook_router"),
        "orders_router": (".orders", "orders_router"),
        "positions_router": (".positions", "positions_router"),
        "risk_router": (".risk", "risk_router"),
        "admin_router": (".admin", "admin_router"),
        "tv_router": (".tv_routes", "tv_router"),
        "visual_router": (".visual_routes", "visual_router"),
        "cdp_router": (".cdp_routes", "cdp_router"),
    }
    if name in _lazy:
        module_path, attr = _lazy[name]
        import importlib

        mod = importlib.import_module(module_path, package=__name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "webhook_router",
    "orders_router",
    "positions_router",
    "risk_router",
    "admin_router",
    "tv_router",
    "visual_router",
    "cdp_router",
]
