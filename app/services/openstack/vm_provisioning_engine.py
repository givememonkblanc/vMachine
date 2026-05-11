"""VM Provisioning Engine — Phase 6.

Async-safe service for OpenStack VM lifecycle operations with timeout handling,
state validation, structured exceptions, operation logging, and Prometheus
instrumentation.

This is NOT a VMware migration engine. This validates OpenStack VM lifecycle
operations directly through Nova APIs.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

from app.clients.openstack.connection import OpenStackConnectionFactory, call_with_timeout
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.metrics.custom import (
    vm_active_count,
    vm_create_duration,
    vm_create_failures,
    vm_lifecycle_operations,
)
from app.common.utils.serializers import serialize_resource
from app.schemas.openstack.vm_lifecycle import VMCreateRequest, VMDetail, VMOperationResponse

logger = logging.getLogger("vm_provisioning_engine")

VALID_STATE_TRANSITIONS: dict[str, list[str]] = {
    "start": ["SHUTOFF", "STOPPED", "SUSPENDED", "ERROR"],
    "stop": ["ACTIVE", "PAUSED"],
    "reboot": ["ACTIVE"],
    "delete": ["ACTIVE", "SHUTOFF", "STOPPED", "ERROR", "SUSPENDED"],
}

PROVISIONING_TIMEOUT = 300.0
LIFECYCLE_TIMEOUT = 120.0
SERVER_POLL_INTERVAL = 3.0


class VMProvisioningEngine:
    """Async VM lifecycle operations against OpenStack Nova.

    Every public method is async-safe, uses ``call_with_timeout`` to avoid
    blocking the event loop, and records Prometheus metrics.
    """

    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_vm(self, request: VMCreateRequest) -> VMDetail:
        """Create a VM and wait until it reaches ACTIVE or an error state."""
        t0 = time.monotonic()
        logger.info("Creating VM name=%s flavor=%s image=%s", request.name, request.flavor_id, request.image_id)

        server = None
        try:
            server = await self._nova_call("create_server", PROVISIONING_TIMEOUT,
                name=request.name,
                image_id=request.image_id,
                flavor_id=request.flavor_id,
                networks=[{"uuid": nid} for nid in request.network_ids],
                key_name=request.keypair,
                security_groups=[{"name": sg} for sg in request.security_groups] if request.security_groups else None,
                availability_zone=request.availability_zone,
                metadata=request.metadata,
            )

            server_id = _get_id(server)
            logger.info("VM created id=%s, waiting for ACTIVE state", server_id)

            detail = await self._wait_for_active(server_id, timeout=PROVISIONING_TIMEOUT)
            vm_create_duration.labels(status="success").observe(time.monotonic() - t0)
            vm_active_count.inc()
            logger.info("VM id=%s is ACTIVE (%.1fs)", server_id, time.monotonic() - t0)
            return detail

        except Exception as exc:
            elapsed = time.monotonic() - t0
            error_type = type(exc).__name__
            vm_create_duration.labels(status="failed").observe(elapsed)
            vm_create_failures.labels(error_type=error_type).inc()
            logger.error("VM creation failed after %.1fs: %s", elapsed, exc)
            if server is not None:
                sid = _get_id(server)
                await self._cleanup_failed_server(sid)
            raise

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    async def start_vm(self, server_id: str) -> VMOperationResponse:
        return await self._lifecycle_operation(server_id, "start")

    async def stop_vm(self, server_id: str) -> VMOperationResponse:
        return await self._lifecycle_operation(server_id, "stop")

    async def reboot_vm(self, server_id: str) -> VMOperationResponse:
        return await self._lifecycle_operation(server_id, "reboot")

    async def delete_vm(self, server_id: str) -> VMOperationResponse:
        t0 = time.monotonic()
        logger.info("Deleting VM id=%s", server_id)
        try:
            detail = await self.get_vm(server_id)
            _validate_state(detail.status, "delete")

            await self._nova_call("delete_server", LIFECYCLE_TIMEOUT, server_id, ignore_missing=True)

            try:
                await self._wait_for_deleted(server_id, timeout=60.0)
            except Exception:
                pass

            elapsed = time.monotonic() - t0
            vm_lifecycle_operations.labels(operation="delete", status="success").inc()
            vm_active_count.dec()
            logger.info("VM id=%s deleted (%.1fs)", server_id, elapsed)
            return VMOperationResponse(server_id=server_id, operation="delete", status="success", elapsed_seconds=elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            vm_lifecycle_operations.labels(operation="delete", status="failed").inc()
            error_type = type(exc).__name__
            logger.error("Delete VM id=%s failed after %.1fs: %s (%s)", server_id, elapsed, exc, error_type)
            raise

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def get_vm(self, server_id: str) -> VMDetail:
        server = await self._nova_call("get_server", LIFECYCLE_TIMEOUT, server_id)
        if not server:
            raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
        return _serialize_vm(server)

    async def list_vms(self) -> list[VMDetail]:
        servers = await self._nova_call("servers", LIFECYCLE_TIMEOUT)
        return [_serialize_vm(s) for s in servers]

    async def get_active_count(self) -> int:
        servers = await self.list_vms()
        active = sum(1 for s in servers if s.status == "ACTIVE")
        vm_active_count.set(active)
        return active

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _lifecycle_operation(self, server_id: str, operation: str) -> VMOperationResponse:
        t0 = time.monotonic()
        logger.info("Operation %s on VM id=%s", operation, server_id)
        try:
            detail = await self.get_vm(server_id)
            _validate_state(detail.status, operation)

            sdk_method = _operation_to_sdk(operation)
            await self._nova_call(sdk_method, LIFECYCLE_TIMEOUT, server_id)

            elapsed = time.monotonic() - t0
            vm_lifecycle_operations.labels(operation=operation, status="success").inc()
            logger.info("VM id=%s %s succeeded (%.1fs)", server_id, operation, elapsed)
            return VMOperationResponse(
                server_id=server_id, operation=operation, status="success", elapsed_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            vm_lifecycle_operations.labels(operation=operation, status="failed").inc()
            error_type = type(exc).__name__
            logger.error("VM id=%s %s failed after %.1fs: %s (%s)", server_id, operation, elapsed, exc, error_type)
            raise

    async def _nova_call(self, method: str, timeout: float, *args: Any, **kwargs: Any) -> Any:
        conn = self.factory.create()
        sdk = getattr(conn, "compute", None)
        if sdk is None:
            raise OpenStackIntegrationException("OpenStack compute service not available")
        fn = getattr(sdk, method, None)
        if fn is None:
            raise OpenStackIntegrationException(f"Unknown compute method: {method}")
        return await call_with_timeout(fn, *args, timeout=timeout, **kwargs)

    async def _wait_for_active(self, server_id: str, timeout: float) -> VMDetail:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            detail = await self.get_vm(server_id)
            if detail.status == "ACTIVE":
                return detail
            if detail.status in ("ERROR", "UNKNOWN"):
                raise AppException(
                    message=f"VM entered {detail.status} state during provisioning",
                    status_code=500,
                    error_code="vm_provisioning_failed",
                )
            await _async_sleep(SERVER_POLL_INTERVAL)
        raise TimeoutError(f"VM {server_id} did not reach ACTIVE within {timeout}s")

    async def _wait_for_deleted(self, server_id: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                await self.get_vm(server_id)
            except AppException as exc:
                if exc.status_code == 404:
                    return
                raise
            await _async_sleep(SERVER_POLL_INTERVAL)
        logger.warning("VM id=%s did not disappear within %.1fs (may still be deleting)", server_id, timeout)

    async def _cleanup_failed_server(self, server_id: str) -> None:
        try:
            await self._nova_call("delete_server", 30.0, server_id, ignore_missing=True)
            logger.info("Cleaned up failed VM id=%s", server_id)
        except Exception as exc:
            logger.warning("Failed to clean up VM id=%s: %s", server_id, exc)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _validate_state(current_status: str, operation: str) -> None:
    allowed = VALID_STATE_TRANSITIONS.get(operation, [])
    if current_status not in allowed:
        raise AppException(
            message=f"Cannot {operation} VM in state '{current_status}' (allowed: {allowed})",
            status_code=409,
            error_code="invalid_state_transition",
        )


def _operation_to_sdk(operation: str) -> str:
    mapping = {
        "start": "start_server",
        "stop": "stop_server",
        "reboot": "reboot_server",
        "delete": "delete_server",
    }
    sdk = mapping.get(operation)
    if sdk is None:
        raise AppException(message=f"Unsupported operation: {operation}", status_code=400, error_code="invalid_operation")
    return sdk


def _extract_reference_id(value: object) -> str | None:
    if isinstance(value, Mapping):
        rid = value.get("id")
        return str(rid) if rid is not None else None
    rid = getattr(value, "id", None)
    return str(rid) if rid is not None else None


def _extract_addresses(value: object) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, list[str]] = {}
    for net_name, entries in value.items():
        if not isinstance(net_name, str) or not isinstance(entries, list):
            continue
        ips: list[str] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            addr = entry.get("addr")
            if isinstance(addr, str):
                ips.append(addr)
        result[net_name] = ips
    return result


def _get_id(server: object) -> str:
    sid = getattr(server, "id", None)
    if sid:
        return str(sid)
    raise OpenStackIntegrationException("Server object has no id attribute")


def _serialize_vm(server: object) -> VMDetail:
    data = serialize_resource(server, ["id", "name", "status", "created", "updated", "key_name",
                                        "availability_zone", "progress"])
    metadata_raw = getattr(server, "metadata", None) or {}
    metadata = {str(k): str(v) for k, v in metadata_raw.items()} if isinstance(metadata_raw, Mapping) else {}

    # Determine power state
    power_state = None
    os_ext_st = getattr(server, "OS-EXT-STS", None)
    if isinstance(os_ext_st, Mapping):
        power_state = os_ext_st.get("power_state")
    if power_state is None:
        vm_state = getattr(server, "vm_state", None)
        power_state = str(vm_state) if vm_state else None

    return VMDetail(
        **data,
        flavor_id=_extract_reference_id(getattr(server, "flavor", None)),
        image_id=_extract_reference_id(getattr(server, "image", None)),
        addresses=_extract_addresses(getattr(server, "addresses", None)),
        metadata=metadata,
        power_state=str(power_state) if power_state is not None else None,
    )


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
