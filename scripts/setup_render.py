#!/usr/bin/env python3
"""Setup Render services via API."""
import httpx, json, sys

API_KEY = "rnd_NxIu2UQ5ZOfCnIBE1qpKL58ceZZK"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json", "Content-Type": "application/json"}
BASE = "https://api.render.com/v1"

def api(method, path, data=None):
    url = f"{BASE}{path}"
    if method == "get":
        r = httpx.get(url, headers=HEADERS)
    elif method == "post":
        r = httpx.post(url, headers=HEADERS, json=data)
    elif method == "patch":
        r = httpx.patch(url, headers=HEADERS, json=data)
    else:
        r = httpx.request(method, url, headers=HEADERS, json=data)
    return r.json()

# List existing services
print("=== EXISTING SERVICES ===")
services = api("get", "/services")
for svc in services:
    s = svc.get("service", svc)
    print(f"  {s.get('id')} | {s.get('name')} | {s.get('type')} | {s.get('status')}")

# Find graxia-backend
backend = None
for svc in services:
    s = svc.get("service", svc)
    if s.get("name") == "graxia-backend":
        backend = s
        break

if not backend:
    print("\nNo graxia-backend found. Creating one...")
    # Create web service with Docker
    payload = {
        "owner": {"id": "tea-d8qqg1j6sc1c73acpjk0", "type": "team"},
        "name": "graxia-backend",
        "type": "web",
        "repo": "https://github.com/bravforcode/graxia-os.git",
        "branch": "main",
        "service_details": {
            "runtime": "docker",
            "dockerfilePath": "./backend/Dockerfile",
            "env": "docker",
            "healthCheckPath": "/health",
            "envVars": [
                {"key": "APP_ENV", "value": "production"},
                {"key": "REQUIRE_SUPABASE", "value": "false"},
                {"key": "SCHEDULER_EMBEDDED", "value": "false"},
                {"key": "COOKIE_SECURE", "value": "true"},
                {"key": "FRONTEND_URL", "value": "https://graxia-os-funnel.vercel.app"},
                {"key": "ALLOWED_CORS_ORIGINS", "value": "https://graxia-os-funnel.vercel.app"},
                {"key": "CORS_ORIGINS", "value": "https://graxia-os-funnel.vercel.app"},
                {"key": "APP_HOST", "value": "graxia-backend.onrender.com"},
                {"key": "APP_BASE_URL", "value": "https://graxia-backend.onrender.com"},
                {"key": "LOG_LEVEL", "value": "INFO"},
                {"key": "SECRET_KEY", "value": "6a9e545a123d72d743dcff1f7a3eca7a0998830803a6dccf4ccd08b8bffa0d38"},
                {"key": "ENCRYPTION_KEY", "value": "72ac46ef02709831b84f74db1a2af7d9856295ca4442b660df1b57e6a47b4102"},
                {"key": "CSRF_SECRET", "value": "ac68d0b6c3f51f7c6cf2a458be52cbd34aee6c032c1f472de8bc791f20273d3c"},
                {"key": "ADMIN_API_KEY", "value": "GEWCidADpbOTa0LRcQ3ks6UPMxI8r1eKmzf74ZVlnBJugqvN"},
                {"key": "STRIPE_SECRET_KEY", "value": "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"},
                {"key": "STRIPE_PUBLISHABLE_KEY", "value": "pk_live_51SwptU0u86vWnztX10iyngMpKUSK5ODTffKqgAunP2MyaqieGaI0PxHUhOUIfv6R9PsuWnT10qDgglctbZ0tk91L00zBLGeuL6"},
                {"key": "STRIPE_WEBHOOK_SECRET", "value": "whsec_ZhkAp6OrT6c5nOYRqpN7hg9lPUKFuo38"},
                {"key": "STRIPE_PRICE_STARTER_MONTHLY", "value": "price_1Tk8sg0u86vWnztX9dXtypOV"},
                {"key": "STRIPE_PRICE_PRO_MONTHLY", "value": "price_1Tk8si0u86vWnztXmgV4gEpM"},
                {"key": "STRIPE_PRICE_ENTERPRISE_MONTHLY", "value": "price_1Tk8sj0u86vWnztXXtiM9M2C"},
            ],
        },
    }
    result = api("post", "/services", payload)
    print(f"  Created: {result}")
    backend = result.get("service", result)

print(f"\n=== BACKEND SERVICE ===")
print(f"  ID: {backend.get('id')}")
print(f"  Name: {backend.get('name')}")
print(f"  Status: {backend.get('status')}")
print(f"  URL: {backend.get('service_details', {}).get('url', 'N/A')}")

# Update env vars with secrets
if backend.get("id"):
    print(f"\n=== UPDATING ENV VARS ===")
    env_vars = [
        {"key": "SECRET_KEY", "value": "6a9e545a123d72d743dcff1f7a3eca7a0998830803a6dccf4ccd08b8bffa0d38"},
        {"key": "ENCRYPTION_KEY", "value": "72ac46ef02709831b84f74db1a2af7d9856295ca4442b660df1b57e6a47b4102"},
        {"key": "CSRF_SECRET", "value": "ac68d0b6c3f51f7c6cf2a458be52cbd34aee6c032c1f472de8bc791f20273d3c"},
        {"key": "ADMIN_API_KEY", "value": "GEWCidADpbOTa0LRcQ3ks6UPMxI8r1eKmzf74ZVlnBJugqvN"},
        {"key": "STRIPE_SECRET_KEY", "value": "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"},
        {"key": "STRIPE_PUBLISHABLE_KEY", "value": "pk_live_51SwptU0u86vWnztX10iyngMpKUSK5ODTffKqgAunP2MyaqieGaI0PxHUhOUIfv6R9PsuWnT10qDgglctbZ0tk91L00zBLGeuL6"},
        {"key": "STRIPE_WEBHOOK_SECRET", "value": "whsec_ZhkAp6OrT6c5nOYRqpN7hg9lPUKFuo38"},
        {"key": "STRIPE_PRICE_STARTER_MONTHLY", "value": "price_1Tk8sg0u86vWnztX9dXtypOV"},
        {"key": "STRIPE_PRICE_PRO_MONTHLY", "value": "price_1Tk8si0u86vWnztXmgV4gEpM"},
        {"key": "STRIPE_PRICE_ENTERPRISE_MONTHLY", "value": "price_1Tk8sj0u86vWnztXXtiM9M2C"},
    ]
    for ev in env_vars:
        result = api("patch", f"/services/{backend['id']}/env-vars", {"envVars": [ev]})
        status = "OK" if not result.get("error") else f"ERROR: {result['error']}"
        print(f"  {ev['key']}: {status}")

    # Trigger deploy
    print(f"\n=== TRIGGERING DEPLOY ===")
    deploy_result = api("post", f"/services/{backend['id']}/deploys", {})
    print(f"  Deploy: {deploy_result.get('id', deploy_result)}")
