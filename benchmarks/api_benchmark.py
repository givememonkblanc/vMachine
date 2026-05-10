import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime

import httpx

ENDPOINTS = [
    {"method": "GET", "path": "/api/v1/health", "name": "Health Check"},
    {"method": "GET", "path": "/api/v1/compute/servers", "name": "List Servers"},
    {"method": "GET", "path": "/api/v1/image/images", "name": "List Images"},
    {"method": "GET", "path": "/api/v1/network/networks", "name": "List Networks"},
    {"method": "GET", "path": "/api/v1/storage/volumes", "name": "List Volumes"},
    {"method": "GET", "path": "/api/v1/kubernetes/clusters", "name": "List K8s Clusters"},
]

async def measure_endpoint(client: httpx.AsyncClient, endpoint: dict, iterations: int) -> dict:
    method = endpoint["method"]
    path = endpoint["path"]
    name = endpoint["name"]
    
    latencies = []
    successes = 0
    failures = 0
    
    for _ in range(iterations):
        start_time = time.perf_counter()
        try:
            response = await client.request(method, path)
            response.raise_for_status()
            successes += 1
        except Exception:
            failures += 1
        finally:
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000)
            
    if not latencies:
        return {}
        
    latencies.sort()
    
    return {
        "name": name,
        "endpoint": f"{method} {path}",
        "success_rate": (successes / iterations) * 100,
        "failure_rate": (failures / iterations) * 100,
        "min_ms": latencies[0],
        "max_ms": latencies[-1],
        "avg_ms": statistics.mean(latencies),
        "p50_ms": statistics.median(latencies),
        "p95_ms": statistics.quantiles(latencies, n=20)[18],
        "p99_ms": statistics.quantiles(latencies, n=100)[98],
    }

async def run_benchmark(base_url: str, iterations: int):
    results = []
    
    print(f"Starting benchmark against {base_url} ({iterations} iterations per endpoint)...")
    
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        for endpoint in ENDPOINTS:
            print(f"Benchmarking {endpoint['name']} ({endpoint['method']} {endpoint['path']})...")
            result = await measure_endpoint(client, endpoint, iterations)
            if result:
                results.append(result)
                
    print("\n--- Benchmark Results ---")
    print(f"{'API Name':<20} | {'Avg (ms)':<8} | {'p50 (ms)':<8} | {'p95 (ms)':<8} | {'p99 (ms)':<8} | {'Min (ms)':<8} | {'Max (ms)':<8} | {'Success %'}")
    print("-" * 110)
    for r in results:
        print(f"{r['name']:<20} | {r['avg_ms']:<8.2f} | {r['p50_ms']:<8.2f} | {r['p95_ms']:<8.2f} | {r['p99_ms']:<8.2f} | {r['min_ms']:<8.2f} | {r['max_ms']:<8.2f} | {r['success_rate']:.1f}%")
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark_results_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vMachine API Benchmark Tool")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL of the vMachine API")
    parser.add_argument("--iterations", type=int, default=50, help="Number of requests per endpoint")
    args = parser.parse_args()
    
    asyncio.run(run_benchmark(args.base_url, args.iterations))
