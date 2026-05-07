"""
graxia/services/revenue_os_api/__init__.py
Revenue OS API service package.

NOTE: Do NOT eagerly import `app` or `create_app` here.
Importing this package is a transitive side-effect of importing any submodule
(e.g. middleware, dependencies, routers). If `app` is imported here it will
trigger the full router registration chain at package-load time, which causes
FastAPI route validation to run before test/dev environments are ready.

To get the app:
    from graxia.services.revenue_os_api.app import app, create_app
"""
