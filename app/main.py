import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.common.exceptions.handlers import register_exception_handlers
from app.common.middleware.audit import AuditMiddleware
from app.common.middleware.request_id import RequestIDMiddleware
from app.core.config.settings import get_settings
from app.events import on_shutdown, on_startup
from app.services.core.audit_service import audit_flush_worker, drain_audit_queue, enqueue_shutdown_signal
from app.services.monitoring.monitoring_service import enqueue_metric_shutdown, metric_flush_worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    audit_flush = asyncio.create_task(audit_flush_worker())
    metric_flush = asyncio.create_task(metric_flush_worker())
    await on_startup()
    yield
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
    return app


app = create_application()
