from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.common.exceptions.handlers import register_exception_handlers
from app.common.middleware.audit import AuditMiddleware
from app.common.middleware.request_id import RequestIDMiddleware
from app.core.config.settings import get_settings
from app.events import on_shutdown, on_startup


@asynccontextmanager
async def lifespan(_: FastAPI):
    await on_startup()
    yield
    await on_shutdown()


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
