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
# VMware connection pool metrics
# ---------------------------------------------------------------------------

vmw_pool_size = Gauge(
    name="vmware_connection_pool_size",
    documentation="Current VMware connection pool size.",
)

vmw_conn_created = Counter(
    name="vmware_connections_created_total",
    documentation="Total VMware connections created.",
)

vmw_conn_reused = Counter(
    name="vmware_connections_reused_total",
    documentation="Total VMware connections reused from pool.",
)

vmw_conn_reconnected = Counter(
    name="vmware_connections_reconnected_total",
    documentation="Total VMware stale connections reconnected.",
)

vmw_conn_failed = Counter(
    name="vmware_connections_failed_total",
    documentation="Total VMware connection failures.",
)

# ---------------------------------------------------------------------------
# VMware assessment metrics
# ---------------------------------------------------------------------------

vmw_assessment_total = Counter(
    name="vmware_assessment_total",
    documentation="Total VMware assessment requests by status.",
    labelnames=("status",),
)

vmw_plan_total = Counter(
    name="vmware_plan_total",
    documentation="Total VMware migration plan requests by status.",
    labelnames=("status",),
)

vmw_inventory_sync_duration = Histogram(
    name="vmware_inventory_sync_duration_seconds",
    documentation="VMware inventory sync duration.",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

vmw_inventory_stale_count = Gauge(
    name="vmware_inventory_stale_count",
    documentation="Stale (uncached) VMware inventory items.",
    labelnames=("resource_type",),
)

# ---------------------------------------------------------------------------
# Phase 5 — Observability expansion metrics
# ---------------------------------------------------------------------------

vmw_vcenter_api_duration = Histogram(
    name="vmware_vcenter_api_duration_seconds",
    documentation="vCenter API call latency by operation.",
    labelnames=("operation",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

vmw_openstack_api_duration = Histogram(
    name="vmware_openstack_api_duration_seconds",
    documentation="OpenStack API call latency during mapping validation.",
    labelnames=("service", "operation"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0, 30.0),
)

vmw_assessment_queue_depth = Gauge(
    name="vmware_assessment_queue_depth",
    documentation="Current number of queued parallel assessment tasks.",
)

vmw_assessment_timeouts_total = Counter(
    name="vmware_assessment_timeouts_total",
    documentation="Total parallel assessment per-VM timeouts.",
)

vmw_assessment_retries_total = Counter(
    name="vmware_assessment_retries_total",
    documentation="Total assessment operation retries.",
    labelnames=("operation",),
)

vmw_unsupported_hardware_total = Counter(
    name="vmware_unsupported_hardware_total",
    documentation="Total unsupported VM hardware configurations detected.",
    labelnames=("category",),
)
