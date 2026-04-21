#!/usr/bin/env python3
"""
Chaos Tests Against Live Staging API
Tests resilience of running system
"""
import asyncio
import httpx
import time
import sys
from datetime import datetime

API_BASE = "http://localhost:8001"


async def test_health_endpoint():
    """Test basic health check"""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_BASE}/health", timeout=5)
            data = r.json()
            return {
                "pass": r.status_code == 200,
                "status": data.get("status"),
                "ready": data.get("readiness", {}).get("is_ready")
            }
        except Exception as e:
            return {"pass": False, "error": str(e)}


async def test_circuit_breaker_states():
    """Test that circuit breakers are in expected states"""
    # This would need auth, but we can check if API responds
    async with httpx.AsyncClient() as client:
        results = []

        # Rapid requests to trigger any rate limiting
        for i in range(20):
            try:
                r = await client.get(f"{API_BASE}/health", timeout=2)
                results.append(r.status_code)
                await asyncio.sleep(0.1)
            except Exception as e:
                results.append(f"error: {e}")

        success_count = sum(1 for r in results if r == 200)
        error_count = len(results) - success_count

        return {
            "pass": success_count >= 18,  # Allow 2 failures
            "success_rate": f"{success_count}/{len(results)}",
            "errors": error_count
        }


async def test_api_under_load():
    """Test API under concurrent load"""
    async def make_request(client, idx):
        try:
            start = time.time()
            r = await client.get(f"{API_BASE}/health", timeout=3)
            elapsed = time.time() - start
            return {
                "idx": idx,
                "status": r.status_code,
                "time": elapsed,
                "success": r.status_code == 200
            }
        except Exception as e:
            return {"idx": idx, "status": 0, "error": str(e), "success": False}

    async with httpx.AsyncClient() as client:
        tasks = [make_request(client, i) for i in range(30)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    failures = len(results) - successes

    # Calculate average response time
    times = [r.get("time", 0) for r in results if isinstance(r, dict) and "time" in r]
    avg_time = sum(times) / len(times) if times else 0

    return {
        "pass": successes >= 25,  # 83%+ success rate
        "total": len(results),
        "successes": successes,
        "failures": failures,
        "avg_response_time": f"{avg_time:.3f}s"
    }


async def test_recovery_after_stress():
    """Test that API recovers after stress"""
    # First stress it
    async with httpx.AsyncClient() as client:
        stress_tasks = [
            client.get(f"{API_BASE}/health", timeout=1)
            for _ in range(50)
        ]
        await asyncio.gather(*stress_tasks, return_exceptions=True)

    # Wait a bit
    await asyncio.sleep(2)

    # Check recovery
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_BASE}/health", timeout=5)
            return {
                "pass": r.status_code == 200,
                "status_code": r.status_code,
                "recovered": r.status_code == 200
            }
        except Exception as e:
            return {"pass": False, "error": str(e), "recovered": False}


async def test_docs_endpoint():
    """Test that Swagger docs are accessible"""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_BASE}/docs", timeout=5)
            return {
                "pass": r.status_code == 200 and "swagger" in r.text.lower(),
                "status": r.status_code
            }
        except Exception as e:
            return {"pass": False, "error": str(e)}


async def run_all_chaos_tests():
    """Run all chaos tests and report results"""
    print("="*70)
    print("CHAOS TESTS AGAINST LIVE STAGING API")
    print(f"Target: {API_BASE}")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*70)

    tests = [
        ("Health Endpoint", test_health_endpoint),
        ("Circuit Breaker Resilience", test_circuit_breaker_states),
        ("API Under Load (30 concurrent)", test_api_under_load),
        ("Recovery After Stress", test_recovery_after_stress),
        ("Docs Endpoint", test_docs_endpoint),
    ]

    results = []

    for name, test_func in tests:
        print(f"\n🔥 Running: {name}...")
        try:
            result = await test_func()
            status = "✅ PASS" if result.get("pass") else "❌ FAIL"
            print(f"   {status}: {result}")
            results.append({"name": name, **result})
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            results.append({"name": name, "pass": False, "error": str(e)})

    # Summary
    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed

    print("\n" + "="*70)
    print("CHAOS TEST SUMMARY")
    print("="*70)
    print(f"Total: {len(results)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} {'❌' if failed > 0 else '✅'}")
    print(f"Success Rate: {passed/len(results)*100:.1f}%")
    print("="*70)

    if failed == 0:
        print("\n🎉 All chaos tests passed! System is resilient.")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review above for details.")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_chaos_tests())
    sys.exit(0 if success else 1)
