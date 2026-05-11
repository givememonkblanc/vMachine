# Benchmark Result Template

## Environment Details
- **Date**: 2026-05-10
- **Target Environment**: Local (connected to real OpenStack/K8s)
- **Server Specifications**: AMD Ryzen 395, 64GB RAM, 1TB NVMe
- **Backend**: uvicorn (single worker) + SQLite
- **Test Duration**: 50 iterations per endpoint (api_benchmark), 3min (Locust)

## API Latency Results (api_benchmark.py — 50 iterations, 2026-05-10)

### Optimized Results (Connection Pooling + Pagination + Timeout/Retry + N+1 Fix + TTL Cache)

| API Name             | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Min (ms) | Max (ms) | Success % |
|----------------------|----------|----------|----------|----------|----------|----------|-----------|
| Health Check         | 0.76     | 0.58     | 1.69     | 5.43     | 0.35     | 5.43     | 100.0%    |
| List Servers         | **10.96**| **0.77** | **1.83** | 505.85   | 0.54     | 505.85   | 100.0%    |
| List Images          | **0.68** | **0.59** | **1.28** | 1.58     | 0.52     | 1.58     | 100.0%    |
| List Networks        | **0.62** | **0.56** | **1.04** | 1.30     | 0.50     | 1.30     | 100.0%    |
| List Volumes         | **3.65** | **0.57** | **1.32** | 149.44   | 0.49     | 149.44   | 100.0%    |
| K8s Cluster Info     | 11.40    | 11.25    | 13.26    | 14.42    | 10.37    | 14.42    | 100.0%    |
| List Migrations      | 2.08     | 1.85     | 4.36     | 6.78     | 1.50     | 6.78     | 100.0%    |

### Before vs After Comparison (SDK Optimization + TTL Cache)

| API Name             | Before (ms) | SDK Opt (ms) | +Cache (ms) | SDK Improve | Cache Improve |
|----------------------|:-----------:|:------------:|:-----------:|:-----------:|:-------------:|
| Health Check         | 3.22        | 0.79         | **0.76**    | -75.5%      | — |
| List Servers         | 577.64      | 403.01       | **10.96**   | -30.2%      | **-97%** |
| List Images          | 299.08      | 116.99       | **0.68**    | -60.9%      | **-99%** |
| List Networks        | 298.86      | 133.57       | **0.62**    | -55.3%      | **-99%** |
| List Volumes         | 348.88      | 136.33       | **3.65**    | -60.9%      | **-97%** |
| K8s Cluster Info     | 15.61       | 12.38        | **11.40**   | -20.7%      | — |
| List Migrations      | 4.30        | 1.83         | **2.08**    | -57.4%      | — |

**Total OpenStack API latency reduction**: SDK 30-61% + Cache **97-99%** (List APIs).
**OpenStack backend API call offload**: **97%** (200 calls → 6 calls over 50 iterations).
**Cache hit ratio**: **97.06%** (3 resources with 96-98% hit rate).

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
- **TTL Cache**: servers=5s, images=30s, networks=30s, volumes=10s (in-memory)
- **Cache Invalidation**: on create/delete server/image/network/volume, volume attach/detach
- **Cache hit ratio**: 97.06% across all cached resources
- **ConnectionReset completely eliminated** (was 22% at 50 health users)
- **502/ConnectionError completely eliminated** (was 87% at 10 servers users)
- **OpenStack backend call offload**: 97% (200→6 OpenStack API calls in 50 iterations)
- **Effective RPS increase**: 31x (2.5→80 RPS for single user cached APIs)
- **New endpoint**: `GET /api/v1/monitoring/cache-stats` for cache observability
- **Remaining bottleneck**: Uvicorn single worker throughput (~90 RPS max)
- See `docs/performance_report.md` for full analysis
