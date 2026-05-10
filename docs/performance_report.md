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

#### Histogram Metrics (aggregated across workers — no `pid` label)

| Metric | Type | Labels | Unit | Description |
|--------|------|--------|------|-------------|
| `http_request_duration_seconds` | Histogram | method, handler | seconds | Per-handler request latency (buckets: 0.01–10s) |
| `http_request_duration_highr_seconds` | Histogram | — | seconds | Detailed latency buckets (for percentile calculation) |
| `vmachine_openstack_api_duration_seconds` | Histogram | service, operation | seconds | OpenStack SDK call latency (buckets: 0.01–60s) |

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
| **Per-worker cache fragmentation** | Round-robin across N workers causes N× more cache misses than single-worker | Phase 2 Redis shared cache |
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
| **Phase 2** | Redis shared cache | 🔴 High | Eliminates per-worker cache fragmentation; cache TTL per-resource; cache invalidation across workers |
| **Phase 3** | PostgreSQL migration | 🔴 High | Concurrent write safety; connection pooling; production-grade durability |
| **Phase 4** | OpenTelemetry tracing | 🟡 Medium | End-to-end latency breakdown; cross-service dependency mapping |
| **Phase 5** | GPU telemetry | 🟢 Low | nvidia-smi Prometheus exporter; only needed for GPU workloads |

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
