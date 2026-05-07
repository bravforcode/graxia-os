#!/usr/bin/env python3
"""
Performance Testing Script for Graxia OS
Tests response times, throughput, and resource usage
"""
import asyncio
import time
import statistics
from typing import List, Dict
import httpx

# Configuration
BASE_URL = "http://localhost:8000"
NUM_REQUESTS = 100
CONCURRENT_REQUESTS = 10

class PerformanceTest:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.results: List[Dict] = []
    
    async def test_endpoint(self, client: httpx.AsyncClient, endpoint: str, method: str = "GET") -> Dict:
        """Test a single endpoint and measure performance"""
        start_time = time.time()
        try:
            if method == "GET":
                response = await client.get(f"{self.base_url}{endpoint}")
            else:
                response = await client.post(f"{self.base_url}{endpoint}")
            
            end_time = time.time()
            duration = (end_time - start_time) * 1000  # Convert to ms
            
            return {
                "endpoint": endpoint,
                "method": method,
                "status": response.status_code,
                "duration_ms": duration,
                "success": 200 <= response.status_code < 300
            }
        except Exception as e:
            end_time = time.time()
            duration = (end_time - start_time) * 1000
            return {
                "endpoint": endpoint,
                "method": method,
                "status": 0,
                "duration_ms": duration,
                "success": False,
                "error": str(e)
            }
    
    async def run_concurrent_tests(self, endpoint: str, num_requests: int, concurrency: int):
        """Run concurrent requests to test throughput"""
        print(f"\n🔥 Testing {endpoint} with {num_requests} requests ({concurrency} concurrent)...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            for _ in range(num_requests):
                task = self.test_endpoint(client, endpoint)
                tasks.append(task)
                
                # Control concurrency
                if len(tasks) >= concurrency:
                    results = await asyncio.gather(*tasks)
                    self.results.extend(results)
                    tasks = []
            
            # Run remaining tasks
            if tasks:
                results = await asyncio.gather(*tasks)
                self.results.extend(results)
    
    def analyze_results(self, endpoint: str):
        """Analyze and print performance metrics"""
        endpoint_results = [r for r in self.results if r["endpoint"] == endpoint]
        
        if not endpoint_results:
            print(f"❌ No results for {endpoint}")
            return
        
        durations = [r["duration_ms"] for r in endpoint_results if r["success"]]
        success_count = sum(1 for r in endpoint_results if r["success"])
        total_count = len(endpoint_results)
        
        if not durations:
            print(f"❌ All requests failed for {endpoint}")
            return
        
        print(f"\n📊 Results for {endpoint}:")
        print(f"   Total Requests: {total_count}")
        print(f"   Successful: {success_count} ({success_count/total_count*100:.1f}%)")
        print(f"   Failed: {total_count - success_count}")
        print(f"\n   Response Times:")
        print(f"   - Min: {min(durations):.2f}ms")
        print(f"   - Max: {max(durations):.2f}ms")
        print(f"   - Mean: {statistics.mean(durations):.2f}ms")
        print(f"   - Median: {statistics.median(durations):.2f}ms")
        
        if len(durations) > 1:
            print(f"   - StdDev: {statistics.stdev(durations):.2f}ms")
            
            # Calculate percentiles
            sorted_durations = sorted(durations)
            p50 = sorted_durations[int(len(sorted_durations) * 0.50)]
            p95 = sorted_durations[int(len(sorted_durations) * 0.95)]
            p99 = sorted_durations[int(len(sorted_durations) * 0.99)]
            
            print(f"\n   Percentiles:")
            print(f"   - p50: {p50:.2f}ms")
            print(f"   - p95: {p95:.2f}ms")
            print(f"   - p99: {p99:.2f}ms")
            
            # Performance rating
            if p95 < 200:
                print(f"   ✅ EXCELLENT (p95 < 200ms)")
            elif p95 < 500:
                print(f"   🟡 GOOD (p95 < 500ms)")
            elif p95 < 1000:
                print(f"   🟠 ACCEPTABLE (p95 < 1000ms)")
            else:
                print(f"   ❌ NEEDS IMPROVEMENT (p95 > 1000ms)")

async def main():
    print("🚀 Graxia OS Performance Testing")
    print("=" * 60)
    
    tester = PerformanceTest()
    
    # Test endpoints
    endpoints = [
        "/health",
        "/api/v1/system/health",
        "/",
    ]
    
    for endpoint in endpoints:
        await tester.run_concurrent_tests(endpoint, NUM_REQUESTS, CONCURRENT_REQUESTS)
        tester.analyze_results(endpoint)
    
    print("\n" + "=" * 60)
    print("✅ Performance testing complete!")
    print("\n📋 Summary:")
    
    all_durations = [r["duration_ms"] for r in tester.results if r["success"]]
    if all_durations:
        print(f"   Overall Mean Response Time: {statistics.mean(all_durations):.2f}ms")
        print(f"   Overall p95 Response Time: {sorted(all_durations)[int(len(all_durations) * 0.95)]:.2f}ms")
        print(f"   Total Successful Requests: {sum(1 for r in tester.results if r['success'])}")
        print(f"   Total Failed Requests: {sum(1 for r in tester.results if not r['success'])}")

if __name__ == "__main__":
    asyncio.run(main())
