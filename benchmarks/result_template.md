# Benchmark Result Template

## Environment Details
- **Date**: 2026-05-10
- **Target Environment**: Local (connected to real OpenStack/K8s)
- **Server Specifications**: AMD Ryzen 395, 64GB RAM, 1TB NVMe
- **Backend**: uvicorn (single worker) + SQLite
- **Test Duration**: 50 iterations per endpoint (api_benchmark), 3min (Locust)

## API Latency Results (api_benchmark.py — 50 iterations, 2026-05-10)

### Optimized Results (Connection Pooling + Pagination + Timeout/Retry)

| API Name             | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Min (ms) | Max (ms) | Success % |
|----------------------|----------|----------|----------|----------|----------|----------|-----------|
| Health Check         | 0.79     | 0.52     | 1.95     | 7.99     | 0.39     | 7.99     | 100.0%    |
| List Servers         | 403.01   | 390.31   | 496.27   | 507.56   | 373.26   | 507.56   | 100.0%    |
| List Images          | 116.99   | 115.32   | 135.62   | 139.28   | 110.05   | 139.28   | 100.0%    |
| List Networks        | 133.57   | 130.69   | 156.56   | 160.91   | 118.04   | 160.91   | 100.0%    |
| List Volumes         | 136.33   | 130.67   | 164.15   | 192.73   | 123.97   | 192.73   | 100.0%    |
| K8s Cluster Info     | 12.38    | 11.22    | 17.42    | 18.76    | 10.87    | 18.76    | 100.0%    |
| List Migrations      | 1.83     | 1.65     | 3.19     | 5.48     | 1.47     | 5.48     | 100.0%    |

### Before vs After Comparison

| API Name             | Before Avg (ms) | After Avg (ms) | Improvement | Key Optimization |
|----------------------|-----------------|----------------|-------------|------------------|
| Health Check         | 3.22            | 0.79           | **-75.5%**  | Connection Pooling |
| List Servers         | 577.64          | 403.01         | **-30.2%**  | Pagination (limit=200) + Pooling |
| List Images          | 299.08          | 116.99         | **-60.9%**  | Pagination (limit=200) + Pooling |
| List Networks        | 298.86          | 133.57         | **-55.3%**  | Pagination (limit=200) + Pooling + N+1 fix |
| List Volumes         | 348.88          | 136.33         | **-60.9%**  | Pagination (limit=200) + Pooling |
| K8s Cluster Info     | 15.61           | 12.38          | **-20.7%**  | Connection Pooling |
| List Migrations      | 4.30            | 1.83           | **-57.4%**  | Connection Pooling |

**Total OpenStack API latency reduction**: 30-61% across all list endpoints.
**Biggest win**: List Volumes (saved 213ms per call) and List Images (saved 182ms per call).

## Load Test Results (Locust — Mixed API, 20 users, 3min)

| Endpoint         | Reqs | Failures | Avg (ms) | p50 (ms) | p95 (ms) | RPS  |
|------------------|------|----------|----------|----------|----------|------|
| Health Check     | 383  | 0        | 2.25     | 2        | 3        | 2.14 |
| List Servers     | 213  | 0        | 610.30   | 600      | 710      | 1.19 |
| List Images      | 143  | 0        | 296.76   | 290      | 330      | 0.80 |
| List Networks    | 137  | 0        | 305.40   | 300      | 340      | 0.77 |
| List Volumes     | 157  | 0        | 378.16   | 370      | 430      | 0.88 |
| Check Migrations | 66   | 0        | 4.94     | 5        | 7        | 0.37 |
| **Aggregated**   | 1,099| **0**    | 250.07   | 290      | 620      | 6.14 |

- **Total Requests**: 1,099
- **Requests Per Second (RPS)**: 6.14
- **Failure Rate**: 0.00%

## System Resource Utilization
> ❌ Not measured in this run. Use `system_monitor.py` in future runs:
> `python benchmarks/system_monitor.py --duration 120 --interval 2`

## Notes / Observations
- **Connection Pooling** (pool_connections=20, pool_maxsize=50) applied to all OpenStack SDK calls via `_build_http_session()`
- **Pagination** (limit=200) applied to all list APIs — dramatically reduces payload for environments with 1000s of resources
- **N+1 query fix** applied to network_service — subnet batch query replaces individual get_subnet() calls
- **Timeout/Retry** configured (60s timeout, up to 2 retries with 0.5s backoff for 429/5xx)
- **30-61% latency improvement** across all OpenStack-dependent endpoints
- See `docs/performance_report.md` for full analysis
