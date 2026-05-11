# vMachine Architecture

*Last updated: 2026-05-11*

## Identity

vMachine = **Compute Asset Control Plane**

- OpenStack 기반 VM/IaaS 관리
- 컴퓨팅 자산 관리
- GPU 서버 자산 관리 준비
- SeaweedFS 연계 가능성
- 운영 배포/성능/관측성 기반 확보

---

## Directory Structure & Roles

```
app/
├── api/              # Presentation layer — HTTP endpoints
│   ├── deps/         #   FastAPI dependency injection
│   ├── router.py     #   Central route registry
│   └── v1/endpoints/ #   Versioned endpoint handlers
│       ├── core/         health, audit
│       ├── identity/     auth, tenants
│       ├── kubernetes/   k8s resources
│       ├── monitoring/   metrics, alerts
│       ├── openstack/    compute, images, networks, volumes, etc.
│       └── orchestration/ clusters, migrations, operations
├── clients/          # External service connections (SDK wrappers)
│   ├── openstack/    #   OpenStackConnectionFactory + call() wrapper
│   ├── kubernetes/   #   Kubernetes API client
│   └── vmware/       #   pyvmomi client for VMware migrations
├── common/           # Shared cross-cutting utilities
│   ├── exceptions/   #   Base exception classes + FastAPI handlers
│   ├── metrics/      #   Prometheus metric definitions
│   ├── middleware/    #   FastAPI middleware (audit, request ID)
│   └── utils/        #   Cache backends, serializers
├── core/             # Application configuration & bootstrapping
│   ├── config/       #   Pydantic Settings (env vars)
│   └── logging/      #   Logging configuration
├── db/               # Database layer
│   ├── base/         #   SQLAlchemy declarative base
│   └── session/      #   Async session factory
├── events/           # Startup/shutdown lifecycle hooks
├── models/           # SQLAlchemy ORM models
├── modules/          # Domain orchestration layer
│   ├── audit/        #   Audit log management
│   ├── auth/         #   Session/auth management
│   ├── cluster/      #   Cluster (OpenStack+K8s) orchestration
│   ├── compute/      #   Compute orchestration (wraps services)
│   ├── flavors/      #   Flavor orchestration
│   ├── health/       #   Health check orchestration
│   ├── images/       #   Image orchestration
│   ├── kubernetes/   #   K8s orchestration
│   ├── migration/    #   VMware→OpenStack migration (direct SDK)
│   ├── monitoring/   #   Monitoring/metrics orchestration
│   ├── networks/     #   Network orchestration
│   ├── orchestration/#   Multi-step orchestration jobs
│   ├── routers/      #   Router orchestration
│   ├── snapshots/    #   Snapshot orchestration
│   ├── subnets/      #   Subnet orchestration
│   ├── tenants/      #   Tenant orchestration
│   └── volumes/      #   Volume orchestration
├── schemas/          # Pydantic request/response models
├── services/         # Core business logic layer
│   ├── core/         #   Audit, operation tasks
│   ├── identity/     #   Auth, tenants
│   ├── kubernetes/   #   K8s resource management
│   ├── monitoring/   #   Metric collection, alerting
│   ├── openstack/    #   OpenStack resource CRUD (via factory.call)
│   └── orchestration/#   Cluster, migration, operations
└── main.py           # FastAPI application factory
```

---

## Layer Responsibilities

### 1. `app/api/` — Presentation Layer

**Role**: HTTP endpoints only. Validate input, call services, return responses.

**Rules**:
- MUST NOT contain business logic
- MUST NOT make SDK or DB calls directly
- MUST import from `app.services.*` (not from `app.modules.*`)
- MAY use `app.api.deps` for dependency injection

### 2. `app/services/` — Business Logic Layer

**Role**: Core domain logic. All OpenStack SDK calls go through `factory.call()`.

**Rules**:
- MUST use `self.factory.call(service, operation, *args, **kwargs)` for all SDK calls
- MUST NOT import from `app.modules.*`
- MAY use `app.common.utils.openstack_cache` for caching
- MAY import from `app.clients.*`, `app.common.*`, `app.schemas.*`

### 3. `app/modules/` — Orchestration Layer

**Role**: Multi-step workflows that span multiple services or external systems.
Built on top of `app/services/`. Used by background workers (`app/worker.py`).

**Rules**:
- MAY import from `app.services.*` and compose multiple service calls
- MAY make direct SDK calls via `factory.call()` (e.g., migration manager)
- MAY use `app.db.session` for database transactions
- SHOULD NOT be imported from `app.api/` (endpoints call services directly)

### 4. `app/clients/` — External Integration Layer

**Role**: SDK connection factories with connection pooling, retry, timeout, and metrics.

**Key classes**:
- `OpenStackConnectionFactory` — cached Keystone auth, HTTP pool, plus `call()` wrapper
- `VMwareClientFactory` — pyvmomi connection management
- Kubernetes client

**`OpenStackConnectionFactory.call()`** provides:
- Duration histogram (`vmachine_openstack_api_duration_seconds`)
- Error counter (`vmachine_openstack_api_errors_total`)
- Consistent `OpenStackIntegrationException` wrapping
- Connection reuse via cached `create()`

### 5. `app/common/` — Shared Utilities

**Key modules**:
- `utils/cache.py` — TTLCache implementation with module-level counters
- `utils/openstack_cache.py` — CacheBackend Protocol + MemoryCacheBackend + public API
- `utils/redis_cache.py` — RedisCache backend (implements CacheBackend Protocol)
- `metrics/custom.py` — Prometheus metric definitions
- `middleware/audit.py` — Request audit logging
- `middleware/request_id.py` — Request ID propagation

### 6. `app/core/` — Configuration

**Key files**:
- `config/settings.py` — Pydantic Settings (env vars via `.env`)
- `logging/logger.py` — Structured logging setup

---

## Cache Architecture

```
                    +-----------------------------+
                    |   Service Layer              |
                    |   cache_get("servers")       |
                    |   cache_set("servers", val)  |
                    |   cache_invalidate("servers")|
                    +----------+------------------+
                               |
                    +----------v------------------+
                    |  openstack_cache.py          |
                    |  CacheBackend Protocol       |
                    |                              |
                    |  MemoryCacheBackend (default) |
                    |    +-- TTLCache per resource  |
                    |                              |
                    |  RedisCache (optional)        |
                    |    +-- CACHE_BACKEND=redis    |
                    +------------------------------+
```

### Backend Selection
- `CACHE_BACKEND=memory` (default): Per-worker in-memory TTLCache
- `CACHE_BACKEND=redis`: Shared Redis cache (all workers)
- Redis failure auto-falls back to memory cache

### Metric Syncing
Cache counters (hits, misses, invalidations) are synced to Prometheus every 15s
via a background task in `app/main.py`. Delta tracking prevents duplicate accumulation.

---

## OpenStack SDK Call Flow

```
Service method
  |
  +-- factory.call("compute", "servers", limit=200)
  |     |
  |     +-- factory.create() -> cached OpenStack SDK Connection
  |     +-- time.monotonic()
  |     +-- conn.compute.servers(limit=200)     <- raw SDK call
  |     +-- openstack_api_duration.observe(...)  <- duration histogram
  |     +-- return result
  |
  +-- cache_set("servers", result)
  +-- return result
```

On error:
```
  factory.call(...)
    -> conn.compute.servers(...) fails
    -> openstack_api_errors.inc(service, error_type)
    -> raise OpenStackIntegrationException(...)
```

---

## Deployment Architecture

```
Systemd (okastro-backend.service)
  |
  +-- PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
  |
  +-- Gunicorn (master)
        |
        +-- Worker 1 (UvicornWorker)
        +-- Worker 2 (UvicornWorker)
        +-- ...
        +-- Worker 8 (UvicornWorker)
              |
              +-- Redis (optional shared cache)
              +-- /tmp/prometheus_multiproc/* (per-worker metrics)

Nginx (:8083) -> Gunicorn (:8002)
```

### Worker Count: 8
Rationale documented in `performance_report.md` (Worker Count Analysis).

### Prometheus Multiprocess
- Counters/Histograms: aggregated across workers (no `pid` label)
- Gauges: per-PID (`{pid="..."}` label)
- Systemd ExecStartPre: cleans `/tmp/prometheus_multiproc/` on restart

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_BACKEND` | `memory` | Cache backend: `memory` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `OPENSTACK_AUTH_URL` | -- | Keystone auth URL |
| `OPENSTACK_USERNAME` | -- | OpenStack admin username |
| `OPENSTACK_PASSWORD` | -- | OpenStack admin password |
| `OPENSTACK_PROJECT_NAME` | -- | OpenStack project (tenant) name |
| `GUNICORN_WORKERS` | 8 | Number of Gunicorn worker processes |
| `GUNICORN_BIND` | `127.0.0.1:8002` | Gunicorn listen address |
| `DATABASE_URL` | `sqlite+aiosqlite:///./okastro.db` | Database connection string |
| `PROMETHEUS_MULTIPROC_DIR` | `/tmp/prometheus_multiproc` | Prometheus multiprocess temp dir |
| `LOG_LEVEL` | `INFO` | Logging level |

Full list in `app/core/config/settings.py`.

---

## Metrics Reference

All exposed at `/metrics` (port 8083 via Nginx, port 8002 direct).

See `performance_report.md` for the complete metric reference table with types and labels.
