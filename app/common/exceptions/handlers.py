from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ExceptionHandler

from app.common.exceptions.base import AppException


async def handle_app_exception(_: Request, exc: Exception) -> JSONResponse:
    app_exception = cast(AppException, exc)
    return JSONResponse(
        status_code=app_exception.status_code,
        content={
            "error": {
                "code": app_exception.error_code,
                "message": app_exception.message,
            }
        },
    )


async def handle_unexpected_exception(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_server_error", "message": str(exc)}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        AppException, cast(ExceptionHandler, handle_app_exception)
    )
    app.add_exception_handler(
        Exception, cast(ExceptionHandler, handle_unexpected_exception)
    )
