# Benchmark Result Template

## Environment Details
- **Date**: 2026-05-10
- **Target Environment**: Local (connected to real OpenStack/K8s)
- **Server Specifications**: AMD Ryzen 395, 64GB RAM, 1TB NVMe
- **Backend**: uvicorn (single worker) + SQLite
- **Test Duration**: 50 iterations per endpoint (api_benchmark), 3min (Locust)

## API Latency Results (api_benchmark.py — 50 iterations, 2026-05-10)

### Optimized Results (Connection Pooling + Pagination + Timeout/Retry + N+1 Fix)

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

## Load Test Results (Locust — Before vs After)

### Health Check (50 users, 2min)

| Metric        | Before      | After       | Change |
|---------------|-------------|-------------|--------|
| Total Reqs    | 10,593      | 10,726      | +1.3%  |
| Failures      | 2,336 (22%) | **0 (0%)**  | ✅     |
| Avg (ms)      | 1.61        | 1           | -38%   |
| RPS           | 88.96       | 89.46       | +0.6%  |
| ConnectionReset | 2,336     | **0**       | ✅     |

### List Servers (10 users, 2min)

| Metric        | Before      | After       | Change |
|---------------|-------------|-------------|--------|
| Total Reqs    | 378         | 349         | -      |
| Failures      | 328 (87%)   | **0 (0%)**  | ✅     |
| Avg (ms)      | ~600        | **436**     | -27%   |
| RPS           | 0.42        | **2.92**    | +595%  |
| 502/ConnectionError | 328 | **0**       | ✅     |

### Mixed API (20 users, 3min)

| Endpoint      | Before Avg | After Avg | Before p95 | After p95 | Failures |
|---------------|:----------:|:---------:|:----------:|:---------:|:--------:|
| List Servers  | 610ms      | **451ms** | 710ms      | **560ms** | **0%**   |
| List Images   | 297ms      | **147ms** | 330ms      | **190ms** | **0%**   |
| List Networks | 305ms      | **155ms** | 340ms      | **200ms** | **0%**   |
| List Volumes  | 378ms      | **160ms** | 430ms      | **200ms** | **0%**   |
| **Aggregated** | **250ms** | **151ms** | **620ms**  | **460ms** | **0%**   |
| **RPS**       | **6.14**   | **6.35**  | —          | —         | —       |

### Step Load (1→100 users, Mixed API)

| Users | Reqs    | Fail% | Avg  | RPS   |
|:----:|:-------:|:-----:|:----:|:-----:|
| 1     | 66      | 0%    | 202  | 0.32  |
| 5     | 335     | 0%    | 187  | 1.60  |
| 10    | 659     | 0%    | 165  | 3.14  |
| 20    | 1,330   | 0.08% | 155  | 6.34  |
| 50    | 3,319   | 0%    | 160  | 15.81 |
| 100   | 6,202   | 0%    | 249  | 29.55 |

## Notes / Observations
- **Connection Pooling** (pool_connections=20, pool_maxsize=50) via `_build_http_session()`
- **Pagination** (limit=200) applied to all list APIs
- **N+1 query fix**: subnet batch query replaces individual get_subnet()
- **Timeout/Retry**: 60s timeout, up to 2 retries with 0.5s backoff for 429/5xx
- **ConnectionReset completely eliminated** (was 22% at 50 health users)
- **502/ConnectionError completely eliminated** (was 87% at 10 servers users)
- **Remaining bottleneck**: Nova API server itself (~350ms of the 403ms total)
- See `docs/performance_report.md` for full analysis
