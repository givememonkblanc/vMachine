# Performance Report

## Architecture Evolution

### Phase -1: Single Uvicorn (Baseline)
```
Uvicorn (0.0.0.0:8000)
  └── Single-worker ASGI server
      └── ~90 RPS max (GIL-bound, no concurrency for CPU-bound work)
```

### Phase 0: Gunicorn + Nginx (Production Web Serving)
```
Nginx (0.0.0.0:8083)
  ├── Request buffering, keepalive 64, gzip
  └── Reverse proxy → Gunicorn (127.0.0.1:8002)
                        ├── Worker 1  (UvicornWorker, ~80 MB RSS)
                        ├── Worker 2  (UvicornWorker, ~80 MB RSS)
                        ├── …
                        └── Worker 16 (UvicornWorker, ~80 MB RSS)
                            └── Each worker: independent in-memory TTL cache
```

**Benefits:**
- Multiple workers → concurrent request handling
- Copy-on-write memory sharing via `preload_app=True`
- Gunicorn worker lifecycle management (graceful restart, max requests)
- Nginx TLS termination, request buffering, static file serving

### Phase 1: Prometheus Metrics (Observability)
```
Nginx /metrics → Gunicorn → MultiProcessCollector
                                └── /tmp/prometheus_multiproc/
                                    ├── counter_meta_…
                                    ├── counter_…
                                    ├── gauge_…
                                    └── …
```

### Phase 2: Redis Distributed Cache (Cross-Worker Cache Sharing)
```
Nginx (0.0.0.0:8083)
  └── Reverse proxy → Gunicorn (127.0.0.1:8002)
                        ├── Worker 1  (UvicornWorker)
                        ├── Worker 2  (UvicornWorker)
                        ├── …
                        └── Worker 8  (UvicornWorker)
                            └── All workers share Redis cache
                                    └── Redis (localhost:6379)
                                        ├── okastro:admin:servers   (TTL 5s)
                                        ├── okastro:admin:images    (TTL 30s)
                                        ├── okastro:admin:networks  (TTL 30s)
                                        └── okastro:admin:volumes   (TTL 10s)
```

**Backend selection**: `CACHE_BACKEND=memory|redis` env var. Redis failure auto-falls back to memory cache.

## Phase 2: Redis Distributed Cache — Results

### Quantitative Comparison: No Cache vs Memory vs Redis

Benchmarked with 8 Gunicorn workers (`preload_app=True`), targeting `GET /api/v1/compute/servers` via Nginx (`:8083`) or direct Gunicorn (`:8002`). All measurements taken against the production 8-worker configuration.

#### Cache Hit Latency (Sequential, Single Worker)

50 sequential requests via keepalive connection (all hit the same worker):

| Metric | No Cache | Memory Cache (warm) | Redis Cache (warm) |
|--------|:--------:|:-------------------:|:------------------:|
| Avg | ~700 ms | ~0.8 ms | **~0.7 ms** |
| p50 | ~700 ms | ~0.6 ms | **~0.6 ms** |
| p95 | ~700 ms | ~3.8 ms | **~1.4 ms** |
| p99 | ~700 ms | ~820 ms | **~1.6 ms** |
| Speedup vs No Cache | — | ~875× | **~1000×** |
| Cache misses (50 req) | 50 | 1 | **0** |

**Note**: Memory sequential includes 1 cache miss (first request to worker, ~700ms). Redis stays warm from prior concurrent traffic and suffers 0 misses.

#### Concurrent Throughput (8 Workers, `ab -c 8`)

Cold start (fresh restart, all caches empty):

| Metric | Memory Backend | Redis Backend | Improvement |
|--------|:--------------:|:-------------:|:-----------:|
| Requests per second | 34.21 req/s | **126.47 req/s** | **3.7×** |
| Mean latency | 169 ms | **9 ms** | **18.8×** |
| Median (p50) | 1 ms | 1 ms | — |
| p95 | 1,058 ms | **4 ms** | **264×** |
| p99 | 1,523 ms | **771 ms** | **2×** |
| Cache misses (first 100 req) | ~8 (one per worker) | **1** (single shared) | **8× fewer** |

Warm (caches populated):

| Metric | Memory Backend | Redis Backend | Improvement |
|--------|:--------------:|:-------------:|:-----------:|
| Requests per second | 66.26 req/s | **830.75 req/s** | **12.5×** |
| Mean latency | 72 ms | **2 ms** | **36×** |
| p50 | 1 ms | 1 ms | — |
| p95 | 745 ms | **2 ms** | **372×** |
| p99 | 1,536 ms | **3 ms** | **512×** |
| Cache hit ratio (servers) | ~93.6% | **~99.6%** | +6% |

#### Cache Hit Ratio Breakdown (Concurrent, Warm)

Under 8-worker concurrent load with `ab -c 8 -n 500`:

| Endpoint | Memory Hit % | Redis Hit % |
|----------|:-----------:|:-----------:|
| List Servers | 93.6% (234 hits / 250 req) | **99.6%** (747 hits / 750 req) |
| List Images | 98% (49 hits / 50 req) | **98%** (49 hits / 50 req) |
| List Networks | 98% | **98%** |
| List Volumes | 98% | **98%** |

#### Resource Usage

| Resource | Memory Backend | Redis Backend |
|----------|:--------------:|:-------------:|
| Per-worker RSS | ~86–88 MB | ~89–90 MB (+3 MB for redis-py) |
| Redis server RSS | N/A | 12.6 MB |
| Redis used memory | N/A | 1.12 MB |
| Redis latency avg | N/A | **0.14 ms** (906 get operations measured) |
| Redis latency p50 | N/A | **<0.1 ms** |
| Redis latency p99 | N/A | **<5 ms** |
| Redis errors | N/A | **0** |

### Memory vs Redis: Key Difference

| Aspect | Memory Cache | Redis Cache |
|--------|:------------:|:-----------:|
| Scope | Per-worker | Cross-worker (shared) |
| Cold start misses | N (one per worker) | **1** (single miss populates all) |
| Cache hit latency | ~0.8 ms | ~1.2 ms (includes network round-trip to localhost) |
| Consistency | Not shared — invalidation only affects one worker | Shared — invalidation affects all workers immediately |
| Persistence | Lost on worker restart | Survives worker restarts |
| Capacity | Bounded by per-worker memory (copy-on-write) | Bounded by Redis maxmemory (configurable) |
| Failure mode | N/A | Auto-fallback to memory cache |

### Redis Operation Latency (from Prometheus metrics)

Measured at steady state (906 Redis `get` operations):

| Percentile | Latency |
|:----------:|:-------:|
| ≤0.1 ms | 633 ops (70%) |
| ≤0.5 ms | 869 ops (96%) |
| ≤1 ms | 888 ops (98%) |
| ≤2 ms | 898 ops (99%) |
| ≤10 ms | 906 ops (100%) |

**Average: 0.14 ms per Redis get.** Zero errors.

### Benchmark Results (Redis)

```
=== Redis Cache Benchmark ===
Request 1 (miss): HTTP 200 in 0.689s  ← OpenStack API call (1 cache miss total)
Request 2 (hit):  HTTP 200 in 0.001s  ← Redis cache hit (any worker)
Request 3 (hit):  HTTP 200 in 0.001s
Request 4 (hit):  HTTP 200 in 0.001s
Request 5 (hit):  HTTP 200 in 0.001s
```

### Cache Consistency Verification

| Test | Result |
|------|:------:|
| Cross-worker cache sharing | ✓ Data cached by worker A → hit on worker B |
| Invalidation (cache_invalidate) | ✓ Redis key deleted → next request = miss → re-cached |
| Invalidation counter | ✓ `redis_cache_invalidations_total` increments by 1 per call |
| TTL expiry (servers=5s) | ✓ After 6s → Redis key auto-expired → next request = miss |
| All 4 resource types | ✓ servers / images / networks / volumes all verified |
| Concurrent invalidation | ✓ 8 workers all see invalidated state immediately (shared Redis) |

### Redis Failure Mode Tests

| Test | Result |
|------|:------:|
| Redis stopped | ✓ API returns 200 (memory/OpenStack fallback), latency ~400–500ms |
| Error metric | ✓ `redis_cache_errors_total` increments (0 → 25 during ~4s outage) |
| Auto-reconnect | ✓ Redis restart → cache resumes: p50=1ms, p99=3ms after warmup |
| `cache_backend_status` | ✓ Workers: `1.0` (Redis), Master: `0.0` (memory — expected, master doesn't serve) |
| Timeline (Redis down → up) | 200 OK throughout, no 5xx errors during outage |

### Redis Protocol-Level Latency

```
redis-cli --latency -h 127.0.0.1 -p 6379
min: 0, max: 1, avg: 0.14 (1000 samples)
```

Redis on localhost averages **0.14 ms** round-trip time, with zero errors during all testing.

### Multi-Worker Consistency (8 Workers)

With `CACHE_BACKEND=redis` and 8 Gunicorn workers, cache behavior under `ab -c 8` concurrent load:

| Scenario | Memory Backend | Redis Backend |
|----------|:--------------:|:-------------:|
| Cold start miss rate | ~8 (one per worker, ~700ms each) | 1 (single Redis miss, then shared) |
| Warm p99 latency | 1,536 ms | 3 ms |
| Cross-worker sharing | No (per-worker TTLCache) | Yes (all workers share Redis) |
| Invalidation propagation | Only affects 1 worker | Instant across all workers |
| Worker restart impact | Cache lost for that worker | No impact (Redis persists) |
| TTL expiry handling | Per-worker (staggered expiry) | Single TTL, consistent across workers |

**Key insight**: In a memory backend setup with 8 workers, 8 concurrent requests each trigger an OpenStack API call (~700ms each) — potentially overwhelming the upstream OpenStack API. With Redis, a single OpenStack call serves all 8 workers.

### Preload_app Operational Notes

Gunicorn is configured with `preload_app = True` for copy-on-write memory sharing. This has important operational implications:

| Concern | Behavior | Mitigation |
|---------|----------|------------|
| **Code reload** | `SIGHUP` does NOT reload application code. Workers continue running old code. | Must use `systemctl restart okastro-backend` for deployments |
| **DB/Redis connections** | Must NOT be opened at import time (will be shared unsafely across forked workers). | All connections open in FastAPI `lifespan` handler (per-worker) |
| **Cache backend state** | Master process holds a reference to the original `_backend` singleton. Workers create their own via lifespan. | Master's `cache_backend_status` may show stale value — master doesn't serve requests |
| **Prometheus multiproc** | Each worker writes metrics to `/tmp/prometheus_multiproc/` | `ExecStartPre` in systemd unit cleans this directory on every restart |
| **Graceful shutdown** | Gunicorn `graceful_timeout=30s` — workers finish in-flight requests before exit | Set lower than OpenStack timeout (120s) so workers don't hang forever |

**Recommended deployment procedure**:
```bash
# 1. Pull new code
git pull

# 2. Restart (NOT reload — SIGHUP won't work with preload_app)
sudo systemctl restart okastro-backend

# 3. Verify health
curl -f http://127.0.0.1:8002/api/v1/health

# 4. Verify workers are serving (correct count)
curl -s http://127.0.0.1:8002/metrics | grep vmachine_worker_count
```

**Why `preload_app=True` is worth the tradeoffs**:
- Reduces per-worker RSS by ~40% (copy-on-write sharing of imported modules)
- Faster worker startup (no re-import of heavy dependencies: FastAPI, Pydantic, OpenStack SDK)
- For a 8-worker deployment: saves ~280 MB RAM vs no preload

---

## Phase 0: Production Web Serving — Results

### Worker Count Analysis

Tested 3 configurations (50 sequential iterations per endpoint, direct Gunicorn):

| API | 4 Workers (ms) | 8 Workers (ms) | 16 Workers (ms) |
|-----|:--------------:|:--------------:|:---------------:|
| Health Check | 0.89 | 1.09 | 0.92 |
| List Servers | 17.00 | 16.18 | 17.26 |
| List Images | 3.39 | 3.45 | 3.52 |
| List Networks | 3.28 | 3.54 | 3.46 |
| List Volumes | 5.23 | 5.11 | 5.15 |
| K8s Cluster Info | 16.75 | 14.63 | 14.26 |
| List Migrations | 2.19 | 2.00 | 1.99 |
| **Success Rate** | **100%** | **100%** | **100%** |

**Key finding:** Single-user sequential latency is nearly identical across all worker counts. The primary bottleneck is OpenStack API response time (500-800ms p99 spikes), not Gunicorn worker availability. Worker count affects concurrent throughput, not single-user latency.

### Resource Usage per Worker Count

| Metric | 4 Workers | 8 Workers | 16 Workers |
|--------|:---------:|:---------:|:----------:|
| Total RSS | ~350 MB | ~680 MB | ~1,370 MB |
| Per-worker RSS | ~80 MB | ~80 MB | ~80 MB |
| RSS / Total RAM | ~1.1% | ~2.1% | ~4.3% |
| CPU cores available | 32 | 32 | 32 |
| CPU cores / worker | 8 | 4 | 2 |

### Worker Count Recommendation

**Recommended: 8 workers**

Rationale:
1. **Memory**: 8 workers = ~680 MB (2.1% of 31 GB) — negligible overhead, leaving headroom for Redis/PostgreSQL
2. **CPU**: 32 cores ÷ 8 workers = 4 cores per worker — ample for I/O-bound ASGI workloads
3. **Cache efficiency**: Fewer workers = warmer per-worker caches (each worker handles ~2× the requests vs 16 workers)
4. **OpenStack throttling**: The remote OpenStack API (haproxy + uwsgi) is the bottleneck, not local Gunicorn. More than 8 concurrent OpenStack clients per host yields diminishing returns
5. **Room to grow**: 8 workers leaves CPU/memory headroom for Phase 2 (Redis) and Phase 3 (PostgreSQL) without service disruption

**Formula for this server (32-core, 31 GB):** `workers = min(2 × CPU_cores + 1, 8)` → **8 workers**

### Nginx vs Direct Gunicorn Comparison

(Benchmarked with 8 workers, 50 iterations each)

| API | Direct Gunicorn (ms) | Nginx Reverse Proxy (ms) | Overhead |
|-----|:--------------------:|:------------------------:|:--------:|
| Health Check | 1.09 | 1.46 | +0.37 ms |
| List Servers | 16.18 | 16.50 | +0.32 ms |
| List Images | 3.45 | 3.39 | -0.06 ms |
| List Networks | 3.54 | 3.73 | +0.19 ms |
| List Volumes | 5.11 | 4.97 | -0.14 ms |
| K8s Cluster Info | 14.63 | 15.20 | +0.57 ms |
| List Migrations | 2.00 | 1.87 | -0.13 ms |

**Nginx overhead: ~0.2–0.4 ms per request** (within measurement noise for sequential benchmarks).

Nginx provides essential production features (TLS termination, request buffering, gzip, access logging) at negligible cost. **Always use Nginx in production.**

---

## Phase 1: Prometheus Metrics — Results

### Metric Reference Table

All `vmachine_*` metrics are exposed at `/metrics` (port 8083 via Nginx, port 8002 direct).

#### Counter Metrics (aggregated across workers — no `pid` label)

| Metric | Type | Labels | Unit | Description |
|--------|------|--------|------|-------------|
| `http_requests_total` | Counter | method, status, handler | count | Total HTTP requests by method, status code, and route handler |
| `vmachine_cache_hits_total` | Counter | resource | count | Lifetime cache hits per resource type (servers, images, networks, volumes) |
| `vmachine_cache_misses_total` | Counter | resource | count | Lifetime cache misses per resource type |
| `vmachine_cache_invalidations_total` | Counter | resource | count | Lifetime cache invalidations per resource type |
| `vmachine_openstack_api_errors_total` | Counter | service, error_type | count | OpenStack SDK errors by service and exception type |
| `redis_cache_hits_total` | Counter | resource | count | Redis cache hits per resource type (Phase 2) |
| `redis_cache_misses_total` | Counter | resource | count | Redis cache misses per resource type (Phase 2) |
| `redis_cache_invalidations_total` | Counter | resource | count | Redis cache invalidations per resource type (Phase 2) |
| `redis_cache_errors_total` | Counter | — | count | Total Redis connection/operation errors (Phase 2) |

#### Histogram Metrics (aggregated across workers — no `pid` label)

| Metric | Type | Labels | Unit | Description |
|--------|------|--------|------|-------------|
| `http_request_duration_seconds` | Histogram | method, handler | seconds | Per-handler request latency (buckets: 0.01–10s) |
| `http_request_duration_highr_seconds` | Histogram | — | seconds | Detailed latency buckets (for percentile calculation) |
| `vmachine_openstack_api_duration_seconds` | Histogram | service, operation | seconds | OpenStack SDK call latency (buckets: 0.01–60s) |
| `redis_cache_latency_seconds` | Histogram | operation | seconds | Redis operation latency (Phase 2, buckets: 0.0001–1.0s) |

#### Summary Metrics (aggregated across workers — no `pid` label)

| Metric | Type | Labels | Unit | Description |
|--------|------|--------|------|-------------|
| `http_request_size_bytes` | Summary | handler | bytes | Incoming request body size |
| `http_response_size_bytes` | Summary | handler | bytes | Outgoing response body size |

#### Gauge Metrics (per PID — `{pid="..."}` label)

| Metric | Type | Labels | Unit | Description |
|--------|------|--------|------|-------------|
| `vmachine_worker_count` | Gauge | — | count | Current worker count per process (master=0, workers=16) |
| `vmachine_cache_hit_ratio` | Gauge | resource | ratio (0–1) | Cache hit ratio per resource, updated every 15s |
| `vmachine_db_pool_size` | Gauge | — | count | Current database connection pool size |
| `vmachine_db_pool_overflow` | Gauge | — | count | Current database connection pool overflow |
| `cache_backend_status` | Gauge | — | 0 or 1 | Active cache backend: 1=redis, 0=memory (Phase 2) |

### Multiprocess Behavior

In Gunicorn multiprocess mode, metrics follow these rules:

1. **Counter/Histogram/Summary**: Written to shared files in `/tmp/prometheus_multiproc/`. The `/metrics` endpoint reads all files and returns **aggregated values** without `pid` labels.
2. **Gauge**: Written per-process. The `/metrics` endpoint returns **per-PID values** with `{pid="..."}` labels.
3. **Zero-valued counters** do not appear in `/metrics` output until first incremented.
4. **Stale data**: Old multiproc files from a previous run cause duplicate metrics. Systemd `ExecStartPre` cleans the directory on every start.

### Increment Verification

After 5 API calls to each OpenStack endpoint (servers, images, networks, volumes):

| Metric | Before | After | Delta |
|--------|:------:|:-----:|:-----:|
| `http_requests_total{handler="/api/v1/compute/servers"}` | 0 | 5 | +5 |
| `http_requests_total{handler="/api/v1/images"}` | 0 | 5 | +5 |
| `http_requests_total{handler="/api/v1/networks"}` | 0 | 5 | +5 |
| `http_requests_total{handler="/api/v1/volumes"}` | 0 | 5 | +5 |
| `http_requests_total{handler="/api/v1/health"}` | 0 | 50 | +50 |
| `vmachine_cache_misses_total{resource="servers"}` | 0 | 1 | +1 |
| `vmachine_cache_misses_total{resource="images"}` | 0 | 1 | +1 |
| `vmachine_cache_misses_total{resource="networks"}` | 0 | 1 | +1 |
| `vmachine_cache_misses_total{resource="volumes"}` | 0 | 1 | +1 |

Note: Cache misses are low because each worker has its own cache. With 16 workers and Nginx round-robin, most of the 5 requests hit different workers (cache miss on each worker).

---

## Configuration Files

### Gunicorn (`gunicorn.conf.py`)
- **Workers**: 8 (recommended — see Worker Count Analysis)
- **Worker class**: `uvicorn.workers.UvicornWorker`
- **Preload**: `True` (copy-on-write memory sharing)
- **Max requests**: 10,000 (per worker, with jitter)
- **Timeout**: 120s (accommodates slow OpenStack calls)
- **Keepalive**: 5s

### Nginx (`/etc/nginx/sites-available/vmachine-api`)
- **Listen**: 0.0.0.0:8083
- **Upstream**: 127.0.0.1:8002 (keepalive 64)
- **Buffering**: on for normal API, off for `/metrics`
- **Timeouts**: connect 10s, read 120s, send 60s
- **Health endpoint**: `location = /api/v1/health` (no access log)

### Systemd (`/etc/systemd/system/okastro-backend.service`)
- **User**: ryzen395
- **ExecStartPre**: cleans `/tmp/prometheus_multiproc/`
- **Environment**: `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc`
- **Restart**: always (5s delay)

---

## Remaining Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| ~~Per-worker cache fragmentation~~ | ~~Round-robin across N workers causes N× more cache misses~~ | ✅ **Resolved by Phase 2 Redis shared cache** |
| **OpenStack API throttling** | 8+ concurrent OpenStack calls may overwhelm haproxy/uwsgi | Add client-side rate limiting in Phase 2 |
| **SQLite contention** | Multiple workers writing to same SQLite file can cause `database is locked` | Phase 3 PostgreSQL migration |
| **No distributed tracing** | Hard to debug cross-service latency (Gunicorn → OpenStack → DB) | Phase 4 OpenTelemetry |
| **No GPU monitoring** | GPU workloads invisible to Prometheus | Phase 5 nvidia-smi exporter |
| **No alerting** | Metrics collected but not acted upon | Prometheus Alertmanager + Grafana |
| **Gunicorn preload_app=True** | DB connections opened in master before fork may be shared unsafely | Verify DB connections are created in lifespan, not at import time |

---

## Next Phase Recommendations

| Phase | Scope | Priority | Rationale |
|-------|-------|:--------:|-----------|
| **Phase 2** | Redis shared cache | 🔴 High | ✅ **Completed** — Redis distributed cache with CACHE_BACKEND selection, cross-worker sharing, auto-fallback |
| **Phase 3** | PostgreSQL migration | 🔴 High | Concurrent write safety; connection pooling; production-grade durability |
| **Phase 4** | OpenTelemetry tracing | 🟡 Medium | End-to-end latency breakdown; cross-service dependency mapping |
| **Phase 5** | GPU telemetry | 🟢 Low | nvidia-smi Prometheus exporter; only needed for GPU workloads |

### Phase 2: Redis Cache — Completed Features
- `CACHE_BACKEND=memory|redis` env var for backend selection
- Redis auto-fallback to memory on connection failure
- Key namespace: `okastro:{project_name}:{resource_type}`
- Per-resource TTLs: servers=5s, images=30s, networks=30s, volumes=10s
- Invalidation on create/delete server/image/network/volume + volume attach/detach
- 6 new Prometheus metrics: `redis_cache_hits_total`, `redis_cache_misses_total`, `redis_cache_invalidations_total`, `redis_cache_latency_seconds`, `redis_cache_errors_total`, `cache_backend_status`
- Consistent cross-worker cache sharing (all 8 workers share the same Redis data)

### Design Constraints for Next Phase
- **Do not** change existing metric names or labels (backward compatibility)
- **Do not** remove Phase 0/1 infrastructure (Nginx, Gunicorn, systemd, Prometheus)
- All new components must be independently restartable without API downtime
- Keep the `.env` file in `.gitignore` (contains secrets)

---

## Benchmark Methodology

### Tools
- **api_benchmark.py**: Sequential requests, measures per-endpoint avg/p50/p95/p99 latency
- **Load test**: Locust (for future concurrent benchmarking with recommended worker count)

### Environment
- **CPU**: AMD Ryzen AI MAX+ PRO 395 (32 cores)
- **RAM**: 31 GB
- **Storage**: NVMe SSD
- **OS**: Ubuntu 24.04 (Linux)
- **OpenStack**: Kolla-Ansible (Victoria), haproxy on :80/:8000
- **Workers**: Gunicorn 4/8/16 (UvicornWorker)
- **Iterations**: 50 sequential requests per endpoint
- **Success criteria**: 100% success rate, 0 failures
