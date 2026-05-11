from collections.abc import Awaitable, Callable
from uuid import uuid4

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing_extensions import override


class RequestIDMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id

        # Propagate request_id into the current OpenTelemetry span so that
        # all child spans (OpenStack SDK calls, DB queries, cache ops)
        # inherit it via span context.
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("http.request_id", request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
