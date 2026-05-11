"""Custom Prometheus metric definitions for vMachine.

Usage
-----
Registered automatically in ``app.main`` via the instrumentator lifecycle.
These metrics supplement the default HTTP metrics provided by
``prometheus-fastapi-instrumentator``.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# API-level metrics
# ---------------------------------------------------------------------------

openstack_api_duration = Histogram(
    name="vmachine_openstack_api_duration_seconds",
    documentation="Latency of OpenStack SDK backend calls per service.",
    labelnames=("service", "operation"),
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

openstack_api_errors = Counter(
    name="vmachine_openstack_api_errors_total",
    documentation="Total OpenStack SDK errors by service and exception type.",
    labelnames=("service", "error_type"),
)

# ---------------------------------------------------------------------------
# Cache metrics
# ---------------------------------------------------------------------------

# These mirror the counters in app.common.utils.cache but are persisted
# across Gunicorn worker restarts via Prometheus multiprocess mode.
cache_hits = Counter(
    name="vmachine_cache_hits_total",
    documentation="Cache hits by resource type.",
    labelnames=("resource",),
)

cache_misses = Counter(
    name="vmachine_cache_misses_total",
    documentation="Cache misses by resource type.",
    labelnames=("resource",),
)

cache_invalidations = Counter(
    name="vmachine_cache_invalidations_total",
    documentation="Cache invalidations by resource type.",
    labelnames=("resource",),
)

# snapshot gauge updated periodically by a background task
cache_hit_ratio = Gauge(
    name="vmachine_cache_hit_ratio",
    documentation="Current cache hit ratio (0.0 – 1.0).",
    labelnames=("resource",),
)

# ---------------------------------------------------------------------------
# System-level metrics
# ---------------------------------------------------------------------------

worker_count = Gauge(
    name="vmachine_worker_count",
    documentation="Number of active Gunicorn worker processes.",
)

db_pool_size = Gauge(
    name="vmachine_db_pool_size",
    documentation="Current database connection pool size.",
)

db_pool_overflow = Gauge(
    name="vmachine_db_pool_overflow",
    documentation="Current database connection pool overflow connections.",
)

# ---------------------------------------------------------------------------
# Redis cache metrics
# ---------------------------------------------------------------------------

redis_cache_hits = Counter(
    name="redis_cache_hits_total",
    documentation="Redis cache hits by resource type.",
    labelnames=("resource",),
)

redis_cache_misses = Counter(
    name="redis_cache_misses_total",
    documentation="Redis cache misses by resource type.",
    labelnames=("resource",),
)

redis_cache_invalidations = Counter(
    name="redis_cache_invalidations_total",
    documentation="Redis cache invalidations by resource type.",
    labelnames=("resource",),
)

redis_cache_latency = Histogram(
    name="redis_cache_latency_seconds",
    documentation="Redis cache operation latency.",
    labelnames=("operation",),
    buckets=(0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0),
)

redis_cache_errors = Counter(
    name="redis_cache_errors_total",
    documentation="Total Redis cache errors.",
)

cache_backend_status = Gauge(
    name="cache_backend_status",
    documentation="Active cache backend: 1=redis, 0=memory",
)

# ---------------------------------------------------------------------------
# VMware assessment metrics
# ---------------------------------------------------------------------------

vmware_assessment_total = Counter(
    name="vmachine_vmware_assessment_total",
    documentation="Total VMware assessments performed.",
    labelnames=("result",),
)

vmware_migration_plans = Counter(
    name="vmachine_vmware_migration_plans_total",
    documentation="Total migration plans generated.",
)

vmware_inventory_sync_duration = Histogram(
    name="vmachine_vmware_inventory_sync_duration_seconds",
    documentation="Duration of VMware inventory sync operations.",
    buckets=(1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

vmware_inventory_size = Gauge(
    name="vmachine_vmware_inventory_size",
    documentation="Number of resources in VMware inventory by type.",
    labelnames=("resource_type",),
)
