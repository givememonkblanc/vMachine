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
