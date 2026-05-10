# Benchmark Result Template

## Environment Details
- **Date**: 2026-05-10
- **Target Environment**: Local (connected to real OpenStack/K8s)
- **Server Specifications**: AMD Ryzen 395, 64GB RAM, 1TB NVMe
- **Backend**: uvicorn (single worker) + SQLite
- **Test Duration**: 50 iterations per endpoint (api_benchmark), 3min (Locust)

## API Latency Results (api_benchmark.py — 50 iterations, 2026-05-10)

| API Name             | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Min (ms) | Max (ms) | Success % |
|----------------------|----------|----------|----------|----------|----------|----------|-----------|
| Health Check         | 3.22     | 0.99     | 4.86     | 92.78    | 0.52     | 92.78    | 100.0%    |
| List Servers         | 577.64   | 567.90   | 671.56   | 714.49   | 546.86   | 714.49   | 100.0%    |
| List Images          | 299.08   | 288.21   | 396.89   | 434.98   | 277.56   | 434.98   | 100.0%    |
| List Networks        | 298.86   | 296.16   | 307.77   | 423.46   | 286.28   | 423.46   | 100.0%    |
| List Volumes         | 348.88   | 342.50   | 400.76   | 410.72   | 325.66   | 410.72   | 100.0%    |
| K8s Cluster Info     | 15.61    | 12.36    | 18.28    | 148.85   | 11.68    | 148.85   | 100.0%    |
| List Migrations      | 4.30     | 3.35     | 11.15    | 11.66    | 1.99     | 11.66    | 100.0%    |

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
- All 7 APIs returned 100% success rate after endpoint path fix (was returning 404 due to wrong routes)
- OpenStack Nova (List Servers) is the heaviest endpoint at ~570ms avg — bottleneck is Nova API latency, not vMachine
- Single uvicorn worker saturates at ~90 RPS for health check endpoint (connection resets at 50 users)
- OpenStack Nova shows 502 errors under sustained 10-user load — needs Connection Pool tuning
- See `docs/performance_report.md` for full analysis
