#!/usr/bin/env python3
"""
Get authentication token for staging API testing
Uses dev bypass mode for easy testing
"""
import asyncio
import httpx
import json
import sys

API_BASE = "http://localhost:8001"


async def get_auth_token(email: str = "test@staging.local", password: str = "anypassword"):
    """
    Get auth token from staging API
    
    The staging API uses DEV BYPASS mode which:
    - Auto-creates users if not exists
    - Skips password verification
    - Returns valid tokens immediately
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE}/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "user": data.get("user"),
                    "token_type": data.get("token_type", "bearer")
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


async def test_protected_endpoints(token: str):
    """Test protected endpoints with the token"""
    headers = {"Authorization": f"Bearer {token}"}
    endpoints = [
        "/api/v1/system/health/detailed",
        "/api/v1/system/resilience/status",
        "/api/v1/system/scraper-health",
    ]
    
    results = []
    async with httpx.AsyncClient() as client:
        for endpoint in endpoints:
            try:
                r = await client.get(
                    f"{API_BASE}{endpoint}",
                    headers=headers,
                    timeout=5
                )
                results.append({
                    "endpoint": endpoint,
                    "status": r.status_code,
                    "success": r.status_code == 200,
                    "preview": r.text[:200] if r.status_code == 200 else r.text[:100]
                })
            except Exception as e:
                results.append({
                    "endpoint": endpoint,
                    "status": 0,
                    "success": False,
                    "error": str(e)
                })
    
    return results


async def main():
    print("="*70)
    print("GET AUTH TOKEN FOR STAGING API")
    print("="*70)
    
    # Get token
    print("\n[1] Getting auth token...")
    result = await get_auth_token("staging-test@gracia.local")
    
    if not result["success"]:
        print(f"❌ Failed: {result['error']}")
        sys.exit(1)
    
    token = result["access_token"]
    user = result["user"]
    
    print(f"✅ Success!")
    print(f"   User: {user.get('email')} (ID: {user.get('id')})")
    print(f"   Role: {user.get('role')}")
    print(f"\n   Access Token (first 50 chars):")
    print(f"   {token[:50]}...")
    
    # Test protected endpoints
    print("\n[2] Testing protected endpoints...")
    results = await test_protected_endpoints(token)
    
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"   {status} {r['endpoint']}")
        if r["success"]:
            print(f"      Response: {r['preview']}...")
        else:
            print(f"      Error: {r.get('error', r.get('preview'))}")
    
    # Save token to file
    print("\n[3] Saving token to staging-token.json...")
    import json
    with open("staging-token.json", "w") as f:
        json.dump({
            "access_token": token,
            "refresh_token": result["refresh_token"],
            "user": user,
            "api_base": API_BASE,
            "created_at": str(asyncio.get_event_loop().time())
        }, f, indent=2)
    
    # Show curl example
    print("\n" + "="*70)
    print("CURL EXAMPLES WITH AUTH TOKEN")
    print("="*70)
    print(f"""
# Detailed Health (with circuit breaker status)
curl -H "Authorization: Bearer {token}" \
  http://localhost:8001/api/v1/system/health/detailed

# Resilience Score
curl -H "Authorization: Bearer {token}" \
  http://localhost:8001/api/v1/system/resilience/status

# Scraper Health
curl -H "Authorization: Bearer {token}" \
  http://localhost:8001/api/v1/system/scraper-health

# Test Predictive Alerts
curl -X POST -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{{"service": "test", "metrics": {{"latency_ms": [10,50,120,280,500,900]}}}}' \
  http://localhost:8001/api/v1/system/health/predictive-test
""")
    
    print("="*70)
    print("Token saved to: staging-token.json")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
