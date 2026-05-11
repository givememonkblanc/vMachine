import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from datetime import datetime

import httpx

ENDPOINTS = [
    {"method": "GET", "path": "/api/v1/health", "name": "Health Check", "enabled": True},
    {"method": "GET", "path": "/api/v1/compute/servers", "name": "List Servers", "enabled": True},
    {"method": "GET", "path": "/api/v1/images", "name": "List Images", "enabled": True},
    {"method": "GET", "path": "/api/v1/networks", "name": "List Networks", "enabled": True},
    {"method": "GET", "path": "/api/v1/volumes", "name": "List Volumes", "enabled": True},
    {"method": "GET", "path": "/api/v1/k8s/cluster", "name": "Get K8s Cluster Info", "enabled": True},
    {"method": "GET", "path": "/api/v1/migrations", "name": "List Migrations", "enabled": True},
    {"method": "GET", "path": "/api/v1/vmware/vms", "name": "VMware VMs (cold)", "enabled": True},
    {"method": "GET", "path": "/api/v1/vmware/datastores", "name": "VMware Datastores (cold)", "enabled": True},
    {"method": "GET", "path": "/api/v1/vmware/networks", "name": "VMware Networks (cold)", "enabled": True},
    {"method": "GET", "path": "/api/v1/vmware/assessments", "name": "VMware Assessments (cold)", "enabled": True},
    {"method": "GET", "path": "/api/v1/vmware/plans", "name": "VMware Plans (cold)", "enabled": True},
]

async def measure_endpoint(client: httpx.AsyncClient, endpoint: dict, iterations: int) -> dict:
    method = endpoint["method"]
    path = endpoint["path"]
    name = endpoint["name"]
    
    success_latencies = []
    error_latencies = []
    status_codes = defaultdict(int)
    
    for _ in range(iterations):
        start_time = time.perf_counter()
        try:
            response = await client.request(method, path)
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            status_codes[response.status_code] += 1
            if 200 <= response.status_code < 300:
                success_latencies.append(latency_ms)
            else:
                error_latencies.append(latency_ms)
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            status_codes[type(e).__name__] += 1
            error_latencies.append(latency_ms)
            
    successes = len(success_latencies)
    failures = len(error_latencies)
    
    success_latencies.sort()
    
    return {
        "name": name,
        "endpoint": f"{method} {path}",
        "total_requests": iterations,
        "success_rate": (successes / iterations) * 100,
        "failure_rate": (failures / iterations) * 100,
        "status_codes": dict(status_codes),
        "success_metrics": {
            "avg_ms": statistics.mean(success_latencies) if successes > 0 else 0,
            "p50_ms": statistics.median(success_latencies) if successes > 0 else 0,
            "p95_ms": statistics.quantiles(success_latencies, n=20)[18] if successes >= 20 else (success_latencies[-1] if successes > 0 else 0),
            "p99_ms": statistics.quantiles(success_latencies, n=100)[98] if successes >= 100 else (success_latencies[-1] if successes > 0 else 0),
            "min_ms": success_latencies[0] if successes > 0 else 0,
            "max_ms": success_latencies[-1] if successes > 0 else 0,
        },
        "error_metrics": {
            "avg_ms": statistics.mean(error_latencies) if failures > 0 else 0,
            "count": failures
        }
    }

async def run_benchmark(base_url: str, iterations: int):
    results = []
    
    print(f"Starting benchmark against {base_url} ({iterations} iterations per endpoint)...")
    
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        for endpoint in [ep for ep in ENDPOINTS if ep.get("enabled", True)]:
            print(f"Benchmarking {endpoint['name']} ({endpoint['method']} {endpoint['path']})...")
            result = await measure_endpoint(client, endpoint, iterations)
            results.append(result)
                
    print("\n--- Successful Responses Latency ---")
    print(f"{'API Name':<25} | {'Avg (ms)':<8} | {'p50 (ms)':<8} | {'p95 (ms)':<8} | {'p99 (ms)':<8} | {'Success %'}")
    print("-" * 80)
    for r in results:
        sm = r["success_metrics"]
        print(f"{r['name']:<25} | {sm['avg_ms']:<8.2f} | {sm['p50_ms']:<8.2f} | {sm['p95_ms']:<8.2f} | {sm['p99_ms']:<8.2f} | {r['success_rate']:.1f}%")
        
    print("\n--- Error Responses Summary ---")
    print(f"{'API Name':<25} | {'Failures':<8} | {'Error Avg (ms)':<15} | {'Status Codes'}")
    print("-" * 80)
    has_errors = False
    for r in results:
        if r["error_metrics"]["count"] > 0:
            has_errors = True
            em = r["error_metrics"]
            codes = ", ".join([f"{k}: {v}" for k, v in r["status_codes"].items() if str(k) not in ["200", "201", "204"]])
            print(f"{r['name']:<25} | {em['count']:<8} | {em['avg_ms']:<15.2f} | {codes}")
    
    if not has_errors:
        print("No errors detected across any endpoints. Perfect!")
        
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
