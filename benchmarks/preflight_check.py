import argparse
import asyncio
import sys
import httpx

ENDPOINTS = [
    {"path": "/api/v1/health", "name": "Health Check"},
    {"path": "/api/v1/compute/servers", "name": "Nova Endpoint (Servers)"},
    {"path": "/api/v1/images", "name": "Glance Endpoint (Images)"},
    {"path": "/api/v1/networks", "name": "Neutron Endpoint (Networks)"},
    {"path": "/api/v1/volumes", "name": "Cinder Endpoint (Volumes)"},
    {"path": "/api/v1/k8s/cluster", "name": "Kubernetes API"},
    {"path": "/api/v1/migrations", "name": "VMware Migration Route"},
]

async def preflight_check(base_url: str):
    print(f"Running Preflight Check against {base_url}...\n")
    print(f"{'Endpoint Name':<30} | {'Path':<30} | {'Status':<10}")
    print("-" * 75)
    
    all_passed = True
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        for ep in ENDPOINTS:
            try:
                response = await client.get(ep["path"])
                if response.status_code == 200:
                    status_text = "PASS"
                else:
                    status_text = f"FAIL ({response.status_code})"
                    all_passed = False
            except Exception as e:
                status_text = f"FAIL ({type(e).__name__})"
                all_passed = False
            print(f"{ep['name']:<30} | {ep['path']:<30} | {status_text:<10}")

    print("\nPreflight Check Result:", "PASS" if all_passed else "FAIL")
    if not all_passed:
        print("Error: Preflight check failed! Please fix the failing endpoints before running benchmarks.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vMachine Preflight Check")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL of the API")
    args = parser.parse_args()
    
    asyncio.run(preflight_check(args.base_url))
