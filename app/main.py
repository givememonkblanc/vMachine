import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.router import api_router
from app.common.exceptions.handlers import register_exception_handlers
from app.common.metrics.custom import (
    cache_backend_status,
    cache_hit_ratio,
    cache_hits,
    cache_invalidations,
    cache_misses,
    redis_cache_errors,
    redis_cache_hits,
    redis_cache_invalidations,
    redis_cache_latency,
    redis_cache_misses,
    worker_count,
)
from app.common.middleware.audit import AuditMiddleware
from app.common.middleware.request_id import RequestIDMiddleware
from app.common.utils.openstack_cache import (
    collect_metrics,
    configure_from_settings,
    is_redis,
)
from app.core.config.settings import get_settings
from app.core.telemetry import init_tracer, register_instrumentations
from app.db.session import init_db_engine
from app.events import on_shutdown, on_startup
from app.services.core.audit_service import (
    audit_flush_worker,
    drain_audit_queue,
    enqueue_shutdown_signal,
)
from app.services.monitoring.monitoring_service import (
    enqueue_metric_shutdown,
    metric_flush_worker,
)


@asynccontextmanager
async def lifespan(app_: FastAPI):
    # Initialize per-worker tracer (must be in lifespan, after Gunicorn fork,
    # so each worker has its own TracerProvider / BatchSpanProcessor).
    settings = get_settings()
    init_tracer()

    audit_flush = asyncio.create_task(audit_flush_worker())
    metric_flush = asyncio.create_task(metric_flush_worker())

    # Initialise database engine (must be in lifespan, not at module level,
    # to avoid asyncpg event-loop conflicts with preload_app=True)
    init_db_engine(settings.database_url)

    # Initialise cache backend (memory or Redis) from settings
    configure_from_settings()
    cache_backend_status.set(1.0 if is_redis() else 0.0)

    # Track last-seen values to compute deltas (avoid duplicate accumulation)
    _last_cache: dict[str, dict[str, int]] = {
        r: {"hits": 0, "misses": 0, "invalidations": 0}
        for r in ("servers", "images", "networks", "volumes")
    }

    # background task: sync in-memory cache counters → Prometheus
    async def _sync_cache_metrics() -> None:
        nonlocal _last_cache
        while True:
            try:
                await asyncio.sleep(15)
                metrics_ = collect_metrics()
                for resource in ("servers", "images", "networks", "volumes"):
                    h = metrics_["hits"].get(resource, 0)
                    m = metrics_["misses"].get(resource, 0)
                    inv = metrics_["invalidations"].get(resource, 0)

                    # Delta since last poll — prevents duplicate accumulation
                    dh = h - _last_cache[resource]["hits"]
                    dm = m - _last_cache[resource]["misses"]
                    dinv = inv - _last_cache[resource]["invalidations"]

                    if dh > 0:
                        cache_hits.labels(resource=resource).inc(dh)
                    if dm > 0:
                        cache_misses.labels(resource=resource).inc(dm)
                    if dinv > 0:
                        cache_invalidations.labels(resource=resource).inc(dinv)

                    total = h + m
                    cache_hit_ratio.labels(resource=resource).set(
                        h / total if total else 1.0
                    )

                    _last_cache[resource] = {
                        "hits": h,
                        "misses": m,
                        "invalidations": inv,
                    }

                # If Redis backend, also sync Redis-specific metrics
                if is_redis():
                    _sync_redis_metrics(metrics_)
            except Exception:
                pass

    cache_sync_task = asyncio.create_task(_sync_cache_metrics())

    # worker count gauge — read from Gunicorn's enviroment
    worker_count.set(int(os.environ.get("GUNICORN_WORKERS", "8")))

    await on_startup()
    yield
    cache_sync_task.cancel()
    try:
        await cache_sync_task
    except asyncio.CancelledError:
        pass
    await on_shutdown()
    await enqueue_shutdown_signal()
    await drain_audit_queue()
    await enqueue_metric_shutdown()
    audit_flush.cancel()
    metric_flush.cancel()
    try:
        await audit_flush
    except asyncio.CancelledError:
        pass
    try:
        await metric_flush
    except asyncio.CancelledError:
        pass


# Helper: sync Redis-specific counters from the metrics snapshot
def _sync_redis_metrics(metrics_: dict) -> None:
    for resource in ("servers", "images", "networks", "volumes"):
        h = metrics_.get("hits", {}).get(resource, 0)
        m = metrics_.get("misses", {}).get(resource, 0)
        v = metrics_.get("invalidations", {}).get(resource, 0)
        if h:
            redis_cache_hits.labels(resource=resource).inc(h)
        if m:
            redis_cache_misses.labels(resource=resource).inc(m)
        if v:
            redis_cache_invalidations.labels(resource=resource).inc(v)

    errs = metrics_.get("redis_errors", 0)
    if errs:
        redis_cache_errors.inc(errs)

    lat_samples = metrics_.get("redis_latency_samples", [])
    if lat_samples:
        for lat in lat_samples:
            redis_cache_latency.labels(operation="get").observe(lat)


def create_application() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)
    app.add_middleware(AuditMiddleware)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
    )
    _ = instrumentator.instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_application()

# Register auto-instrumentations after app creation (module level, before
# Gunicorn fork — the monkey-patches are inherited by all workers, while
# the per-worker TracerProvider is initialized in lifespan).
register_instrumentations(app)
