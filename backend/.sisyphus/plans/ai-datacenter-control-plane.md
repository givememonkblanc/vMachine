# vMachine → AI Datacenter Compute Asset Control Plane

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Balancer (Nginx)                     │
├─────────────────────────────────────────────────────────────┤
│              Gunicorn + UvicornWorker (x workers)            │
├─────────────────────────────────────────────────────────────┤
│  FastAPI App                                                │
│  ├─ Prometheus Instrumentator (metrics)                     │
│  ├─ RequestID Middleware                                    │
│  ├─ Audit Middleware                                        │
│  ├─ Distributed Cache (Redis + In-Memory fallback)          │
│  ├─ OpenStack SDK                                           │
│  ├─ SQLAlchemy 2.0 Async (PostgreSQL via asyncpg)           │
│  └─ VMware Migration Assessment Engine                      │
├─────────────────────────────────────────────────────────────┤
│  Shared: Redis (cache) │ PostgreSQL (DB)                    │
└─────────────────────────────────────────────────────────────┘
```

## Execution Plan (5 Phases)

### Phase 0: Production Web Serving (Gunicorn + Nginx)
**Priority: HIGH | Dependency: None**

- [x] gunicorn.conf.py with UvicornWorker
- [x] Update Dockerfile → Gunicorn
- [x] Nginx reverse proxy config
- [x] Graceful restart, keepalive, timeouts
- [x] Benchmark: single uvicorn vs gunicorn

### Phase 1: Prometheus Metrics
**Priority: HIGH | Dependency: Phase 0**

- [x] Add prometheus-fastapi-instrumentator dependency
- [x] Instrument FastAPI app with default metrics
- [x] Custom metrics: cache hit/miss, OpenStack SDK duration
- [x] Multi-process mode for Gunicorn (`PROMETHEUS_MULTIPROC_DIR`)
- [x] Expose `/metrics` endpoint
- [x] Prometheus scrape config

Supplementary: OpenTelemetry distributed tracing (Phase 2 scope)
- Request ID propagation
- OpenStack SDK call tracing via requests instrumentation
- Cache operation custom spans
- OTLP exporter for Jaeger/Zipkin

### Phase 2: Redis Distributed Cache
**Priority: HIGH | Dependency: Phase 0**

- [x] Redis cache backend class (redis-py async)
- [x] Unified cache interface: in-memory ↔ Redis
- [x] Fallback: Redis down → in-memory only
- [x] Pattern-based invalidation via Redis SCAN
- [x] Tenant-aware namespacing
- [x] Connection pool management
- [x] Benchmark: in-memory vs Redis vs no cache

### Phase 3: PostgreSQL Migration & Operational Stability
**Priority: MEDIUM | Dependency: Phase 0**

- [x] Install asyncpg dependency
- [x] Alembic init and configuration
- [x] Generate initial migration (10 tables)
- [x] Connection pool tuning
- [x] Docker Compose: PostgreSQL container
- [x] Benchmark: SQLite vs PostgreSQL

### Phase 4: VMware Migration Assessment Engine
**Priority: MEDIUM | Dependency: Phase 1, 2**

- [ ] VMware Inventory Schema & vCenter Connectivity
- [ ] VMware Inventory Collection & Sync Service
- [ ] OpenStack Mapping Engine (flavor/network/volume mapping)
- [ ] Migration Assessment API (compatibility, readiness)
- [ ] Migration Plan Service (plan generation, resource estimation)
- [ ] Assessment Metrics
- [ ] Documentation

## Key Architecture Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| **Worker Manager** | Gunicorn + UvicornWorker | Production-grade process management, graceful restart |
| **Workers Formula** | (2 × CPU cores) + 1 | Standard FastAPI recommendation |
| **Worker Class** | UvicornWorker (not H11Worker) | HTTP/1.1 behind Nginx, WebSocket support |
| **Reverse Proxy** | Nginx with proxy_buffering off | SSL termination, static files, rate limiting |
| **Tracing** | OTLP → Jaeger/Zipkin | Supplementary observability (Phase 1 scope) |
| **Metrics** | Prometheus + Grafana | Industry standard for monitoring |
| **Cache** | Redis + in-memory fallback | Production distributed cache with graceful degradation |
| **Cache Strategy** | Cache-aside + stale-while-revalidate | Avoid cache stampedes, serve stale data during refresh |
| **Redis Client** | redis-py 5.x (async) | aioredis merged into redis-py, single library |
| **Database** | PostgreSQL + asyncpg | Production-grade async driver |
| **DB Pool** | pool_size=5, max_overflow=20 | Same as current SQLite config, tested |
| **VMware SDK** | pyVmomi (pyVim) | Official VMware Python SDK, SmartConnect |
| **Inventory Storage** | ResourceSnapshot model + in-memory cache | Existing model reused, no new migration needed |
| **Assessment** | Synchronous assessment per request | No background jobs needed for assessment phase |

## Span Hierarchy (OpenTelemetry)

Supplementary observability — not a dedicated phase.

```
HTTP Request
├── FastAPI Middleware (auto-instrumented)
├── Auth/K8s check
├── OpenStack SDK operation
│   ├── Keystone auth (requests instrumentation)
│   ├── Nova API call (requests instrumentation)
│   │   ├── HTTP request to Nova
│   │   └── Response deserialization
│   ├── Neutron API call (requests instrumentation)
│   ├── Cinder API call (requests instrumentation)
│   └── Glance API call (requests instrumentation)
├── Cache lookup (custom span)
│   ├── Redis GET (redis instrumentation)
│   └── Cache hit/miss attribute
├── Database operation (SQLAlchemy instrumentation)
└── Response serialization (custom span)
```

## Metric Definitions

```python
# API
api_request_duration_seconds      # Histogram: endpoint, method, status
api_requests_total                 # Counter: endpoint, method, status

# OpenStack SDK
openstack_api_duration_seconds    # Histogram: service (nova/neutron/etc), operation
openstack_api_errors_total         # Counter: service, error_type
openstack_api_requests_total       # Counter: service, operation

# Cache
cache_hit_total                    # Counter: resource
cache_miss_total                   # Counter: resource
cache_invalidation_total           # Counter: resource
cache_hit_ratio                    # Gauge: resource (computed)

# Migration Assessment (Phase 4)
assessment_inventory_count         # Gauge: source
assessment_duration_seconds        # Histogram: operation
assessment_compatibility_issues    # Counter: issue_type
assessment_migration_readiness     # Gauge: vm_id (0=draft, 1=ready, 2=blocked)

# System
worker_queue_depth                 # Gauge
db_pool_size                       # Gauge
db_pool_overflow                   # Gauge
```

## New Dependencies

```toml
# Existing (Phase 1-3)
prometheus-fastapi-instrumentator>=7.1.0,<8.0.0
asyncpg>=0.30.0,<1.0.0
redis>=5.3.0,<6.0.0
gunicorn>=23.0.0,<24.0.0

# Supplementary Observability
opentelemetry-api>=1.30.0,<2.0.0
opentelemetry-sdk>=1.30.0,<2.0.0
opentelemetry-instrumentation-fastapi>=0.62b0,<1.0.0
opentelemetry-instrumentation-requests>=0.62b0,<1.0.0
opentelemetry-instrumentation-sqlalchemy>=0.62b0,<1.0.0
opentelemetry-instrumentation-redis>=0.62b0,<1.0.0
opentelemetry-exporter-otlp>=1.30.0,<2.0.0

# Phase 4
pyvmomi>=8.0.0,<9.0.0
```

## Current State vs Target State (After Phase 4)

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Web Server | Gunicorn + 8 workers | Gunicorn + 8 workers | Production-grade |
| Cache | Redis + in-memory | Redis + in-memory | Distributed, HA |
| Database | PostgreSQL (via asyncpg) | PostgreSQL (via asyncpg) | Production-grade |
| Tracing | OpenTelemetry + OTLP | OpenTelemetry + OTLP | Full distributed tracing |
| Metrics | Prometheus + Grafana | Prometheus + Grafana | Complete observability |
| VMware | Basic client (get_vm/export) | Full inventory + assessment | Migration readiness |

## Benchmark Plan

| Phase | Benchmark | Metrics |
|-------|-----------|---------|
| Phase 0 | api_benchmark + Locust | RPS, p95, CPU, Memory, Error rate |
| Phase 2 | api_benchmark | Latency (cache hit vs miss vs no cache) |
| Phase 3 | api_benchmark + Locust | RPS, p95, Connection pooling |
