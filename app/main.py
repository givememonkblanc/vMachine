import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.router import api_router
from app.common.exceptions.handlers import register_exception_handlers
from app.common.metrics.custom import (
    cache_hits,
    cache_misses,
    cache_invalidations,
    cache_hit_ratio,
    worker_count,
)
from app.common.middleware.audit import AuditMiddleware
from app.common.middleware.request_id import RequestIDMiddleware
from app.common.utils.cache import collect_cache_metrics
from app.core.config.settings import get_settings
from app.events import on_shutdown, on_startup
from app.services.core.audit_service import audit_flush_worker, drain_audit_queue, enqueue_shutdown_signal
from app.services.monitoring.monitoring_service import enqueue_metric_shutdown, metric_flush_worker


@asynccontextmanager
async def lifespan(app_: FastAPI):
    audit_flush = asyncio.create_task(audit_flush_worker())
    metric_flush = asyncio.create_task(metric_flush_worker())

    # background task: sync in-memory cache counters → Prometheus
    async def _sync_cache_metrics() -> None:
        while True:
            try:
                await asyncio.sleep(15)
                metrics_ = collect_cache_metrics()
                for resource in ("servers", "images", "networks", "volumes"):
                    h = metrics_["hits"].get(resource, 0)
                    m = metrics_["misses"].get(resource, 0)
                    if h:
                        cache_hits.labels(resource=resource).inc(h)
                    if m:
                        cache_misses.labels(resource=resource).inc(m)
                    inv = metrics_["invalidations"].get(resource, 0)
                    if inv:
                        cache_invalidations.labels(resource=resource).inc(inv)
                    total = h + m
                    cache_hit_ratio.labels(resource=resource).set(h / total if total else 1.0)
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
