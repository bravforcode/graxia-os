"""Debug: why does the public product endpoint return 401?"""
import os, asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["TESTING"] = "true"
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./debug-funnel.db"
os.environ["REDIS_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "8b6e6f1f43a6d96e8f498c1999d3e527d710f63e63283c483d8e578c772091d3"
os.environ["ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

import app.database
import app.models
from app.models.base import Base
from app.middleware.auth import find_route_template, classify_route, AuthLevel, PUBLIC_ROUTES

async def main():
    import app.main as main_mod
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    api_app = main_mod.app

    # Create tables
    async with app.database.engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c))

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        path = "/api/v1/funnel/public/products/11111111-1111-1111-1111-111111111111/public-ebook"
        # Inspect what the middleware sees
        print("PUBLIC_ROUTES contains GET template:",
              ("GET", "/api/v1/funnel/public/products/{organization_id}/{slug}") in PUBLIC_ROUTES)
        # Find matching templates in app
        from starlette.routing import Match
        for route in api_app.router.routes:
            scope = {"type": "http", "method": "GET", "path": path,
                     "headers": [], "query_string": b"", "scheme": "http",
                     "server": ("testserver", 80), "client": ("test", 1)}
            try:
                m, _ = route.matches(scope)
            except Exception:
                continue
            if m == Match.FULL:
                print("FULL-MATCH route:", getattr(route, "path", "?"),
                      "| TYPE:", type(route).__name__,
                      "| has routes:", hasattr(route, "routes"))
                cands = getattr(route, "_effective_candidates", None) or getattr(route, "effective_candidates", None)
                print("  candidates:", type(cands).__name__ if cands is not None else None,
                      "count:", len(cands) if cands else 0)
                for c in (cands or [])[:5]:
                    print("   cand:", type(c).__name__, getattr(c, "path", "<no-path>"))
                print("  _match:", getattr(route, "_match", "<missing>"))
                for cand in ("path", "path_format", "path_template", "regex", "compile"):
                    print("   ", cand, "=", getattr(route, cand, "<missing>"))
        # What does the middleware's own template finder see?
        from starlette.routing import Match as _M
        scope2 = {"type": "http", "method": "GET", "path": path,
                  "headers": [], "query_string": b"", "scheme": "http",
                  "server": ("testserver", 80), "client": ("test", 1)}
        import starlette.requests as sr
        req = sr.Request(scope2)
        scope3 = {"type": "http", "method": "PATCH",
                  "path": "/api/v1/funnel/lead-magnets/11111111-1111-1111-1111-111111111111",
                  "headers": [], "query_string": b"", "scheme": "http",
                  "server": ("testserver", 80), "client": ("test", 1)}
        req3 = sr.Request(scope3)
        t3 = find_route_template(req3)
        print("PATCH lead-magnets template:", t3)
        print("PATCH classify:", classify_route("PATCH", t3 or ""))
        print("find_route_template ->", find_route_template(req))
        print("classify ->", classify_route("GET", find_route_template(req) or path))
        resp = await client.get(path)
        print("STATUS:", resp.status_code)
        print("BODY:", resp.text[:300])

asyncio.run(main())
