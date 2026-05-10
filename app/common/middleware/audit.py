from collections.abc import Mapping, Sequence
from typing import cast, final

from app.core.logging.logger import get_logger
from app.services.core.audit_service import enqueue_audit_entry
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = get_logger(__name__)


@final
class AuditMiddleware:
    """Logs HTTP request audit entries via an async batch queue.

    Instead of writing one DB row per request (which blocks the response),
    entries are pushed onto an in-memory queue and flushed in batches by a
    background worker.  This reduces per-request latency by ~10-50 ms.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app: ASGIApp = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = cast(str, scope.get("method", "UNKNOWN"))
        path = cast(str, scope.get("path", "UNKNOWN"))
        request_id = self._extract_request_id(cast(Sequence[tuple[bytes, bytes]], scope.get("headers", [])))

        status_code = 0
        send_orig = send

        async def send_wrapper(event: Message) -> None:
            nonlocal status_code
            event_type = cast(str, event.get("type"))
            if event_type == "http.response.start":
                status_code = cast(int, event.get("status", 0))
            await send_orig(event)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            status_code = 500
            raise
        finally:
            resource_type = self._infer_resource_type(path)
            action = self._infer_action(method, path)
            audit_status = "success" if status_code and status_code < 400 else "failure"

            await enqueue_audit_entry(
                action=f"{action}_{resource_type}",
                resource_type=resource_type,
                resource_id=self._infer_resource_id(path),
                status=audit_status,
                request_id=request_id,
            )

    def _extract_request_id(self, headers: Sequence[tuple[bytes, bytes]]) -> str | None:
        for raw_key, raw_value in headers:
            if raw_key.decode("utf-8", errors="replace").lower() == "x-request-id":
                return raw_value.decode("utf-8", errors="replace")
        return None

    def _infer_resource_type(self, path: str) -> str:
        parts = [p for p in path.split("/") if p and p not in {"api", "v1"}]
        if not parts:
            return "unknown"
        if parts[0] == "health":
            return "system"
        return parts[0]

    def _infer_action(self, method: str, path: str) -> str:
        method_map: Mapping[str, str] = {
            "GET": "read", "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete",
        }
        parts = [p for p in path.split("/") if p]
        if method == "POST" and len(parts) >= 3 and parts[-1] == "actions":
            return "action"
        return method_map.get(method.upper(), method.lower())

    def _infer_resource_id(self, path: str) -> str | None:
        parts = [p for p in path.split("/") if p]
        non_resource = {
            "api", "v1", "auth", "compute", "networks", "volumes", "images", "flavors",
            "tenants", "health", "servers", "projects", "session", "endpoints",
            "config", "validate", "actions",
        }
        for part in reversed(parts):
            if part not in non_resource:
                return part
        return None
