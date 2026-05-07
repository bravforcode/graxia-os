"""Helpers for building the canonical route manifest."""
from __future__ import annotations

from datetime import UTC, datetime

from app.middleware.auth import classify_route, route_controls


def build_route_manifest(app) -> dict:
    routes: list[dict] = []
    counters = {
        "public": 0,
        "internal": 0,
        "authenticated": 0,
        "operator": 0,
        "admin": 0,
        "blocked": 0,
        "gaps_found": 0,
    }

    for route in app.router.routes:
        path = getattr(route, "path", None)
        methods = sorted(set(getattr(route, "methods", set())) - {"HEAD", "OPTIONS"})
        if not path or not methods:
            continue
        for method in methods:
            expected_auth = classify_route(method, path).value
            gap = expected_auth == ""
            if gap:
                counters["gaps_found"] += 1
            else:
                counters[expected_auth] += 1
            routes.append(
                {
                    "path": path,
                    "method": method,
                    "router_prefix": path.rsplit("/", 1)[0] if "/" in path else path,
                    "expected_auth": expected_auth,
                    "actual_controls": route_controls(method, path),
                    "gap": gap,
                }
            )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": "workspace",
        "routes": sorted(routes, key=lambda item: (item["path"], item["method"])),
        "summary": {
            "total": len(routes),
            "gaps_found": counters["gaps_found"],
            "public": counters["public"],
            "internal": counters["internal"],
            "authenticated": counters["authenticated"],
            "operator": counters["operator"],
            "admin": counters["admin"],
            "blocked": counters["blocked"],
        },
    }
