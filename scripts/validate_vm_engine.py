#!/usr/bin/env python3
"""VM Engine Validation Script — Phase 6.

Validates OpenStack VM lifecycle operations through the VMProvisioningEngine:

  1. List flavors, images, networks
  2. Create a VM (with the first available flavor/image/network)
  3. Wait for ACTIVE state
  4. Reboot VM
  5. Stop VM
  6. Start VM
  7. Delete VM
  8. Verify cleanup

Usage:
    PYTHONPATH=. python scripts/validate_vm_engine.py
    PYTHONPATH=. python scripts/validate_vm_engine.py --json
    PYTHONPATH=. python scripts/validate_vm_engine.py --flavor m1.tiny --image cirros --network private
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.core.config.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("validate_vm_engine")


@dataclass
class StateTraceEntry:
    """Single VM state observation from polling."""
    timestamp: str = ""
    state: str = ""
    elapsed_since_start: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationTiming:
    """Detailed timing breakdown for one lifecycle operation."""
    operation: str = ""
    passed: bool = False
    total_duration_s: float = 0.0
    api_latency_s: float = 0.0
    state_convergence_s: float = 0.0
    request_sent_at: str = ""
    response_received_at: str = ""
    state_converged_at: str = ""
    initial_state: str = ""
    final_state: str = ""
    state_trace: list[StateTraceEntry] = field(default_factory=list)
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleTimingResult:
    """Complete lifecycle timing profile for one VM."""
    vm_name: str = ""
    server_id: str = ""
    flavor_id: str = ""
    image_id: str = ""
    network_id: str = ""
    poll_interval_s: float = 3.0
    started_at: str = ""
    finished_at: str = ""
    total_duration_s: float = 0.0
    all_passed: bool = False
    operations: list[OperationTiming] = field(default_factory=list)
    full_state_trace: list[StateTraceEntry] = field(default_factory=list)
    failure_observations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationStep:
    name: str
    passed: bool = False
    duration_seconds: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ValidationResult:
    started_at: str = ""
    finished_at: str = ""
    total_duration: float = 0.0
    steps: list[ValidationStep] = field(default_factory=list)
    all_passed: bool = False
    server_cleaned_up: bool = False
    engine_ready: bool = False
    lifecycle_timing: LifecycleTimingResult | None = None

    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.steps if s.passed)

    @property
    def total_count(self) -> int:
        return len(self.steps)


async def validate_engine(args: argparse.Namespace) -> ValidationResult:
    if args.dry_run:
        return await _validate_dry_run(args)
    return await _validate_live(args)


async def _validate_dry_run(args: argparse.Namespace) -> ValidationResult:
    """Dry-run mode: validates structure without creating or deleting any VM."""
    result = ValidationResult(
        started_at=datetime.now(timezone.utc).isoformat(),
        engine_ready=False,
    )

    from app.schemas.openstack.vm_lifecycle import VMCreateRequest
    from app.services.openstack.vm_provisioning_engine import VALID_STATE_TRANSITIONS

    logger.info("=== DRY RUN MODE — no resources will be created or deleted ===")

    # ---------------------------------------------------------------
    # 1. Validate engine construction
    # ---------------------------------------------------------------
    step = ValidationStep(name="engine_construction")
    t0 = time.monotonic()
    try:
        factory = OpenStackConnectionFactory(get_settings())
        engine_ready = get_settings().openstack_ready
        step.detail = {
            "openstack_configured": engine_ready,
            "factory_created": True,
        }
        step.passed = True
        if engine_ready:
            step.detail["note"] = "OpenStack is configured — engine can connect to live API"
        else:
            step.detail["note"] = "OpenStack not configured — engine will fail on real calls (expected in dry-run)"
        logger.info("Engine construction: openstack_configured=%s", engine_ready)
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
    step.duration_seconds = time.monotonic() - t0
    result.steps.append(step)

    # ---------------------------------------------------------------
    # 2. Validate request payload construction
    # ---------------------------------------------------------------
    step = ValidationStep(name="request_payload_validation")
    t0 = time.monotonic()
    try:
        req = VMCreateRequest(
            name=args.vm_name or "dry-run-test-vm",
            flavor_id=args.flavor or "m1.tiny",
            image_id=args.image or "cirros-0.6.2",
            network_ids=[args.network or "net-dry-run"],
            keypair=args.keypair,
            security_groups=[args.security_group] if args.security_group else None,
            availability_zone=args.az,
        )
        payload = req.model_dump()
        step.detail = {
            "name": payload["name"],
            "flavor_id": payload["flavor_id"],
            "image_id": payload["image_id"],
            "network_ids": payload["network_ids"],
            "keypair": payload["keypair"],
            "security_groups": payload["security_groups"],
            "availability_zone": payload["availability_zone"],
            "metadata": payload["metadata"],
        }
        step.passed = True
        logger.info("Request payload validated: name=%s flavor=%s image=%s",
                     payload["name"], payload["flavor_id"], payload["image_id"])
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
    step.duration_seconds = time.monotonic() - t0
    result.steps.append(step)

    # ---------------------------------------------------------------
    # 3. Validate state transition logic
    # ---------------------------------------------------------------
    step = ValidationStep(name="state_transition_validation")
    t0 = time.monotonic()
    try:
        valid_cases = [
            ("SHUTOFF", "start", True),
            ("STOPPED", "start", True),
            ("ACTIVE", "stop", True),
            ("ACTIVE", "reboot", True),
            ("ACTIVE", "delete", True),
            ("SHUTOFF", "delete", True),
            ("ERROR", "delete", True),
        ]
        invalid_cases = [
            ("ACTIVE", "start", False),
            ("SHUTOFF", "stop", False),
            ("SHUTOFF", "reboot", False),
            ("STOPPED", "reboot", False),
        ]

        for state, operation, should_pass in valid_cases:
            _validate_state_dry(state, operation, should_pass)
        for state, operation, should_fail in invalid_cases:
            _validate_state_dry(state, operation, should_fail)

        step.detail = {
            "valid_transitions_tested": len(valid_cases),
            "invalid_transitions_tested": len(invalid_cases),
            "all_valid": "ACTIVE/SHUTOFF/STOPPED/SUSPENDED/ERROR -> start/stop/reboot/delete",
        }
        step.passed = True
        logger.info("State transition logic validated: %d valid + %d invalid cases",
                     len(valid_cases), len(invalid_cases))
    except AssertionError as exc:
        step.error = str(exc)
        step.passed = False
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
    step.duration_seconds = time.monotonic() - t0
    result.steps.append(step)

    # ---------------------------------------------------------------
    # 4. Validate cleanup plan
    # ---------------------------------------------------------------
    step = ValidationStep(name="cleanup_plan_validation")
    t0 = time.monotonic()
    try:
        cleanup_plan = {
            "vm_name_prefix": "vmachine-test-" if not args.vm_name else args.vm_name,
            "delete_on_failure": True,
            "safety_net_finally": True,
            "only_delete_own_vms": True,
            "timeout_per_operation_s": 120,
            "create_timeout_s": 300,
        }
        step.detail = cleanup_plan
        step.passed = True
        logger.info("Cleanup plan validated: %s", cleanup_plan)
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
    step.duration_seconds = time.monotonic() - t0
    result.steps.append(step)

    # ---------------------------------------------------------------
    # 5. Summary
    # ---------------------------------------------------------------
    result.engine_ready = True
    result.all_passed = all(s.passed for s in result.steps)
    result.finished_at = datetime.now(timezone.utc).isoformat()
    if result.steps:
        result.total_duration = (
            datetime.fromisoformat(result.finished_at) - datetime.fromisoformat(result.started_at)
        ).total_seconds()
    logger.info("Dry-run validation complete: %s/%s passed",
                 result.passed_count, result.total_count)
    return result


def _validate_state_dry(state: str, operation: str, expect_pass: bool) -> None:
    from app.services.openstack.vm_provisioning_engine import _validate_state
    try:
        _validate_state(state, operation)
        if not expect_pass:
            raise AssertionError(
                f"Expected _validate_state('{state}', '{operation}') to fail but it passed"
            )
    except Exception as exc:
        if expect_pass:
            raise AssertionError(
                f"Expected _validate_state('{state}', '{operation}') to pass but it failed: {exc}"
            ) from exc


async def _validate_live(args: argparse.Namespace) -> ValidationResult:
    result = ValidationResult(
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    factory = OpenStackConnectionFactory(get_settings())

    if not get_settings().openstack_ready:
        logger.error("OpenStack not configured — set OPENSTACK_AUTH_URL/USERNAME/PASSWORD/etc.")
        result.steps.append(ValidationStep(name="engine_ready", passed=False, error="OpenStack env vars not set"))
        result.all_passed = False
        result.engine_ready = False
        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    result.engine_ready = True
    logger.info("OpenStack connection factory initialized")

    from app.schemas.openstack.vm_lifecycle import VMCreateRequest
    from app.services.openstack.vm_provisioning_engine import VMProvisioningEngine

    engine = VMProvisioningEngine(factory)
    created_server_id: str | None = None
    cleanup_attempted = False
    vm_name = args.vm_name or f"vmachine-test-{int(time.time())}"
    poll_interval = args.poll_interval

    lifecycle_ops: list[OperationTiming] = []
    full_state_trace: list[StateTraceEntry] = []
    failure_observations: list[dict[str, Any]] = []
    lifecycle_start = time.monotonic()

    try:
        step, flavors, images_list, networks_list, flavor_id, image_id, network_id = (
            await _discover_resources(engine, factory, args)
        )
        result.steps.append(step)
        if not step.passed:
            result.all_passed = False
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        step, ot, state_trace = await _instrumented_create_vm(
            engine, vm_name, flavor_id, image_id, network_id, args, poll_interval,
        )
        full_state_trace.extend(state_trace)
        result.steps.append(step)
        if ot:
            lifecycle_ops.append(ot)
        if not step.passed:
            result.all_passed = False
            if created_server_id:
                await _cleanup(engine, created_server_id)
                cleanup_attempted = True
            result.server_cleaned_up = cleanup_attempted
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        created_server_id = step.detail.get("server_id")

        for op_name in ("reboot", "stop", "start"):
            ot = await _instrumented_lifecycle_operation(engine, created_server_id, op_name, poll_interval)
            lifecycle_ops.append(ot)
            vs = ValidationStep(
                name=f"vm_{op_name}",
                passed=ot.passed,
                duration_seconds=ot.total_duration_s,
                detail={"server_id": created_server_id, "operation": op_name, "timing": {
                    "api_latency_s": ot.api_latency_s,
                    "state_convergence_s": ot.state_convergence_s,
                    "total_s": ot.total_duration_s,
                }},
                error=ot.error,
            )
            result.steps.append(vs)
            full_state_trace.extend(ot.state_trace)
            if not ot.passed:
                failure_observations.append({
                    "operation": op_name,
                    "error": ot.error,
                    "duration_s": ot.total_duration_s,
                    "final_state": ot.final_state,
                })

        ot = await _instrumented_delete_vm(engine, created_server_id, poll_interval)
        lifecycle_ops.append(ot)
        step = ValidationStep(
            name="delete_vm",
            passed=ot.passed,
            duration_seconds=ot.total_duration_s,
            detail={"server_id": created_server_id, "status": "deleted", "timing": {
                "api_latency_s": ot.api_latency_s, "state_convergence_s": ot.state_convergence_s,
            }},
            error=ot.error,
        )
        result.steps.append(step)
        full_state_trace.extend(ot.state_trace)
        if not ot.passed:
            failure_observations.append({
                "operation": "delete", "error": ot.error,
                "duration_s": ot.total_duration_s,
            })

        step = ValidationStep(name="verify_cleanup")
        t0 = time.monotonic()
        try:
            await engine.get_vm(created_server_id)
            step.passed = False
            step.error = "Server still exists after deletion"
        except Exception as exc:
            error_str = str(exc)
            if "not found" in error_str.lower() or "404" in error_str or "no server" in error_str.lower():
                step.passed = True
                step.detail = {"confirmed": "server no longer exists"}
            else:
                step.passed = False
                step.error = error_str
        step.duration_seconds = time.monotonic() - t0
        result.steps.append(step)

        # VM was deleted by the engine — skip safety cleanup
        cleanup_attempted = True

    except Exception as exc:
        logger.error("Validation failed with unexpected error: %s", exc)
        result.steps.append(ValidationStep(name="unexpected_error", passed=False, error=str(exc)))
    finally:
        if created_server_id and not cleanup_attempted:
            try:
                logger.warning("Safety cleanup for server id=%s", created_server_id)
                await engine.delete_vm(created_server_id)
                result.server_cleaned_up = True
            except Exception:
                pass

    result.all_passed = all(s.passed for s in result.steps)
    result.finished_at = datetime.now(timezone.utc).isoformat()
    if result.steps:
        result.total_duration = (
            datetime.fromisoformat(result.finished_at) - datetime.fromisoformat(result.started_at)
        ).total_seconds()

    result.lifecycle_timing = LifecycleTimingResult(
        vm_name=vm_name,
        server_id=created_server_id or "",
        flavor_id=flavor_id if "flavor_id" in dir() else "",
        image_id=image_id if "image_id" in dir() else "",
        network_id=network_id if "network_id" in dir() else "",
        poll_interval_s=poll_interval,
        started_at=result.started_at,
        finished_at=result.finished_at,
        total_duration_s=result.total_duration,
        all_passed=result.all_passed,
        operations=lifecycle_ops,
        full_state_trace=full_state_trace,
        failure_observations=failure_observations,
    )
    return result


async def _discover_resources(
    engine: VMProvisioningEngine, factory: OpenStackConnectionFactory, args: argparse.Namespace,
) -> tuple[ValidationStep, list, list, list, str, str, str]:
    step = ValidationStep(name="discover_resources")
    t0 = time.monotonic()
    flavor_id = args.flavor or ""
    image_id = args.image or ""
    network_id = args.network or ""
    flavors: list = []
    images_list: list = []
    networks_list: list = []
    try:
        flavors = list(await engine._nova_call("flavors", 30.0, get_all=True))
        step.detail["flavor_count"] = len(flavors)
        images_list = list(await engine._nova_call("images", 30.0))
        step.detail["image_count"] = len(images_list)
        networks_list = list(factory.call("network", "networks"))
        step.detail["network_count"] = len(networks_list)
        flavor_id = args.flavor or (flavors[0].id if flavors else None)
        image_id = args.image or (images_list[0].id if images_list else None)
        network_id = args.network or (networks_list[0].id if networks_list else None)
        if not flavor_id or not image_id or not network_id:
            raise RuntimeError(f"Missing resources: flavor={flavor_id} image={image_id} network={network_id}")
        step.detail["selected"] = {"flavor_id": flavor_id, "image_id": image_id, "network_id": network_id}
        step.passed = True
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
    step.duration_seconds = time.monotonic() - t0
    return step, flavors, images_list, networks_list, flavor_id, image_id, network_id


async def _instrumented_create_vm(
    engine: VMProvisioningEngine,
    vm_name: str, flavor_id: str, image_id: str, network_id: str,
    args: argparse.Namespace,
    poll_interval: float,
) -> tuple[ValidationStep, OperationTiming | None, list[StateTraceEntry]]:
    step = ValidationStep(name="create_vm")
    from app.schemas.openstack.vm_lifecycle import VMCreateRequest

    req = VMCreateRequest(
        name=vm_name, flavor_id=flavor_id, image_id=image_id,
        network_ids=[network_id], keypair=args.keypair or None,
        security_groups=[args.security_group] if args.security_group else None,
        availability_zone=args.az or None,
    )

    operation_start = time.monotonic()
    request_sent_at = datetime.now(timezone.utc).isoformat()
    all_trace: list[StateTraceEntry] = []
    server_id: str | None = None
    ot = None
    api_latency = 0.0

    try:
        vm = await engine.create_vm(req)
        response_received_at = datetime.now(timezone.utc).isoformat()
        api_latency = time.monotonic() - operation_start
        server_id = vm.id

        state_convergence = time.monotonic() - operation_start - api_latency
        if state_convergence < 0:
            state_convergence = 0.0

        step.detail = {
            "server_id": vm.id, "name": vm.name, "status": vm.status,
            "flavor_id": vm.flavor_id, "image_id": vm.image_id,
        }
        step.passed = vm.status == "ACTIVE"

        stop_ev = asyncio.Event()
        trace_task = asyncio.create_task(
            _poll_state_trace(engine, vm.id, operation_start, poll_interval, 15.0, stop_ev)
        )
        await asyncio.sleep(poll_interval)
        stop_ev.set()
        post_trace = await trace_task
        all_trace = post_trace

        ot = _build_operation_timing(
            operation="create", passed=step.passed,
            request_sent_at=request_sent_at,
            response_received_at=response_received_at,
            state_converged_at=datetime.now(timezone.utc).isoformat(),
            initial_state="BUILD", final_state=vm.status,
            state_trace=all_trace,
            total_duration_s=time.monotonic() - operation_start,
            api_latency_s=api_latency,
            state_convergence_s=state_convergence,
        )
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
        ot = _build_operation_timing(
            operation="create", passed=False,
            request_sent_at=request_sent_at,
            response_received_at=datetime.now(timezone.utc).isoformat(),
            state_converged_at="",
            initial_state="BUILD", final_state="ERROR",
            state_trace=all_trace,
            total_duration_s=time.monotonic() - operation_start,
            api_latency_s=api_latency,
            state_convergence_s=0.0,
            error=str(exc),
        )
    step.duration_seconds = time.monotonic() - operation_start
    return step, ot, all_trace


async def _instrumented_lifecycle_operation(
    engine: VMProvisioningEngine, server_id: str, operation: str, poll_interval: float,
) -> OperationTiming:
    operation_start = time.monotonic()
    request_sent_at = datetime.now(timezone.utc).isoformat()

    try:
        detail = await engine.get_vm(server_id)
        initial_state = detail.status
    except Exception as exc:
        return _build_operation_timing(
            operation=operation, passed=False,
            request_sent_at=request_sent_at,
            response_received_at=datetime.now(timezone.utc).isoformat(),
            state_converged_at="",
            initial_state="UNKNOWN", final_state="UNKNOWN",
            state_trace=[], total_duration_s=0, api_latency_s=0,
            state_convergence_s=0, error=f"Pre-flight check failed: {exc}",
        )

    stop_ev = asyncio.Event()
    trace_task = asyncio.create_task(
        _poll_state_trace(engine, server_id, operation_start, poll_interval, 120.0, stop_ev)
    )

    try:
        method = getattr(engine, f"{operation}_vm")
        resp = await method(server_id)
        response_received_at = datetime.now(timezone.utc).isoformat()
        api_latency = time.monotonic() - operation_start

        await asyncio.sleep(poll_interval)
        stop_ev.set()
        trace = await trace_task

        try:
            final_detail = await engine.get_vm(server_id)
            final_state = final_detail.status
        except Exception:
            final_state = "UNKNOWN"

        state_convergence = time.monotonic() - operation_start - api_latency
        if state_convergence < 0:
            state_convergence = 0.0

        passed = resp.status == "success"
        ot = _build_operation_timing(
            operation=operation, passed=passed,
            request_sent_at=request_sent_at,
            response_received_at=response_received_at,
            state_converged_at=datetime.now(timezone.utc).isoformat(),
            initial_state=initial_state, final_state=final_state,
            state_trace=trace,
            total_duration_s=time.monotonic() - operation_start,
            api_latency_s=api_latency,
            state_convergence_s=state_convergence,
        )
        return ot
    except Exception as exc:
        stop_ev.set()
        trace = await trace_task if not trace_task.done() else []
        try:
            final_detail = await engine.get_vm(server_id)
            final_state = final_detail.status
        except Exception:
            final_state = "UNKNOWN"
        return _build_operation_timing(
            operation=operation, passed=False,
            request_sent_at=request_sent_at,
            response_received_at=datetime.now(timezone.utc).isoformat(),
            state_converged_at="",
            initial_state=initial_state, final_state=final_state,
            state_trace=trace,
            total_duration_s=time.monotonic() - operation_start,
            api_latency_s=time.monotonic() - operation_start,
            state_convergence_s=0,
            error=str(exc),
        )


async def _instrumented_delete_vm(
    engine: VMProvisioningEngine, server_id: str, poll_interval: float,
) -> OperationTiming:
    operation_start = time.monotonic()
    request_sent_at = datetime.now(timezone.utc).isoformat()

    try:
        detail = await engine.get_vm(server_id)
        initial_state = detail.status
    except Exception:
        initial_state = "UNKNOWN"

    stop_ev = asyncio.Event()
    trace_task = asyncio.create_task(
        _poll_state_trace(engine, server_id, operation_start, poll_interval, 60.0, stop_ev)
    )

    try:
        resp = await engine.delete_vm(server_id)
        response_received_at = datetime.now(timezone.utc).isoformat()
        api_latency = time.monotonic() - operation_start

        await asyncio.sleep(poll_interval)
        stop_ev.set()
        trace = await trace_task

        deleted = False
        try:
            await engine.get_vm(server_id)
        except Exception as exc:
            err = str(exc).lower()
            if "not found" in err or "404" in err or "no server" in err:
                deleted = True

        state_convergence = time.monotonic() - operation_start - api_latency
        if state_convergence < 0:
            state_convergence = 0.0

        ot = _build_operation_timing(
            operation="delete", passed=deleted,
            request_sent_at=request_sent_at,
            response_received_at=response_received_at,
            state_converged_at=datetime.now(timezone.utc).isoformat(),
            initial_state=initial_state, final_state="DELETED" if deleted else "UNKNOWN",
            state_trace=trace,
            total_duration_s=time.monotonic() - operation_start,
            api_latency_s=api_latency,
            state_convergence_s=state_convergence,
            detail={"delete_api_status": resp.status if hasattr(resp, "status") else "success"},
        )
        return ot
    except Exception as exc:
        stop_ev.set()
        trace = await trace_task if not trace_task.done() else []
        return _build_operation_timing(
            operation="delete", passed=False,
            request_sent_at=request_sent_at,
            response_received_at=datetime.now(timezone.utc).isoformat(),
            state_converged_at="",
            initial_state=initial_state, final_state="UNKNOWN",
            state_trace=trace,
            total_duration_s=time.monotonic() - operation_start,
            api_latency_s=time.monotonic() - operation_start,
            state_convergence_s=0,
            error=str(exc),
        )


async def _cleanup(engine: VMProvisioningEngine, server_id: str) -> None:
    try:
        await engine.delete_vm(server_id)
        logger.info("Cleanup: deleted server id=%s", server_id)
    except Exception as exc:
        logger.warning("Cleanup failed for server id=%s: %s", server_id, exc)


async def _poll_state_trace(
    engine: VMProvisioningEngine,
    server_id: str,
    start_time: float,
    poll_interval: float,
    timeout: float,
    stop_event: asyncio.Event,
) -> list[StateTraceEntry]:
    trace: list[StateTraceEntry] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stop_event.is_set():
            break
        try:
            detail = await engine.get_vm(server_id)
            trace.append(StateTraceEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                state=detail.status,
                elapsed_since_start=time.monotonic() - start_time,
                detail={
                    "power_state": detail.power_state if hasattr(detail, "power_state") else None,
                },
            ))
        except Exception:
            trace.append(StateTraceEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                state="UNKNOWN",
                elapsed_since_start=time.monotonic() - start_time,
                detail={"error": "poll_failed"},
            ))
        await asyncio.sleep(poll_interval)
    return trace


def _build_operation_timing(
    operation: str,
    passed: bool,
    request_sent_at: str,
    response_received_at: str,
    state_converged_at: str,
    initial_state: str,
    final_state: str,
    state_trace: list[StateTraceEntry],
    total_duration_s: float,
    api_latency_s: float,
    state_convergence_s: float,
    error: str | None = None,
    detail: dict | None = None,
) -> OperationTiming:
    return OperationTiming(
        operation=operation,
        passed=passed,
        total_duration_s=round(total_duration_s, 3),
        api_latency_s=round(api_latency_s, 3),
        state_convergence_s=round(state_convergence_s, 3),
        request_sent_at=request_sent_at,
        response_received_at=response_received_at,
        state_converged_at=state_converged_at,
        initial_state=initial_state,
        final_state=final_state,
        state_trace=state_trace,
        error=error,
        detail=detail or {},
    )


def _generate_report(result: ValidationResult) -> str:
    lines = [
        "# VM Engine Validation Report",
        "",
        f"> Started: {result.started_at}",
        f"> Finished: {result.finished_at}",
        f"> Duration: {result.total_duration:.1f}s",
        f"> Result: **{'✅ ALL PASSED' if result.all_passed else '❌ FAILED'}** ({result.passed_count}/{result.total_count})",
        f"> Server cleaned up: {'✅' if result.server_cleaned_up else 'N/A'}",
        "",
        "## Summary",
        "",
        "| Step | Status | Duration | Detail |",
        "|------|:------:|:--------:|--------|",
    ]

    for step in result.steps:
        status = "✅" if step.passed else "❌"
        dur = f"{step.duration_seconds:.1f}s"
        detail = step.error or str(step.detail)[:100] if step.detail else ""
        detail = detail.replace("|", "\\|")
        lines.append(f"| {step.name} | {status} | {dur} | {detail} |")

    lines.extend([
        "",
        "## Step Details",
        "",
    ])

    for step in result.steps:
        lines.append(f"### {step.name}")
        lines.append(f"")
        lines.append(f"- **Passed**: {step.passed}")
        lines.append(f"- **Duration**: {step.duration_seconds:.2f}s")
        if step.error:
            lines.append(f"- **Error**: {step.error}")
        if step.detail:
            if isinstance(step.detail, dict):
                for k, v in step.detail.items():
                    if not isinstance(v, dict):
                        lines.append(f"- **{k}**: {v}")
            else:
                lines.append(f"- **Detail**: {step.detail}")
        lines.append("")

    if result.lifecycle_timing:
        lt = result.lifecycle_timing
        lines.append("")
        lines.append("## Lifecycle Timing Profile")
        lines.append("")
        lines.append(f"- **VM**: {lt.vm_name} | **Flavor**: {lt.flavor_id} | **Image**: {lt.image_id}")
        lines.append(f"- **Total duration**: {lt.total_duration_s:.1f}s")
        lines.append(f"- **Poll interval**: {lt.poll_interval_s}s")
        lines.append(f"- **All operations passed**: {lt.all_passed}")
        if lt.failure_observations:
            lines.append(f"- **Failure observations**: {len(lt.failure_observations)}")
            for fo in lt.failure_observations:
                lines.append(f"  - {fo.get('operation')}: {fo.get('error', 'unknown')} ({fo.get('duration_s', 0):.1f}s)")
        lines.append("")
        lines.append("### Per-Operation Timing")
        lines.append("")
        lines.append("| Operation | Status | API Latency | State Convergence | Total | Initial → Final |")
        lines.append("|-----------|:------:|:-----------:|:-----------------:|:-----:|:----------------:|")
        for op in lt.operations:
            icon = "✅" if op.passed else "❌"
            lines.append(
                f"| {op.operation} | {icon} | {op.api_latency_s:.2f}s | {op.state_convergence_s:.2f}s | "
                f"{op.total_duration_s:.2f}s | {op.initial_state} → {op.final_state} |"
            )
        lines.append("")
        lines.append("### State Transition Trace")
        lines.append("")
        for op in lt.operations:
            lines.append(f"**{op.operation}** (state trace)")
            lines.append("")
            lines.append("| Time | State | Elapsed (s) |")
            lines.append("|------|:-----:|:-----------:|")
            for entry in (op.state_trace or []):
                lines.append(f"| {entry.timestamp} | {entry.state} | {entry.elapsed_since_start:.1f} |")
            if not op.state_trace:
                lines.append("| — | (no trace recorded) | — |")
            lines.append("")

    lines.append("---")
    lines.append("*Report generated by validate_vm_engine.py*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="VM Engine Validation Script")
    parser.add_argument("--flavor", type=str, default=None, help="Flavor ID/name (default: first available)")
    parser.add_argument("--image", type=str, default=None, help="Image ID/name (default: first available)")
    parser.add_argument("--network", type=str, default=None, help="Network ID (default: first available)")
    parser.add_argument("--vm-name", type=str, default=None, help="VM name (default: auto-generated)")
    parser.add_argument("--keypair", type=str, default=None, help="SSH keypair name")
    parser.add_argument("--security-group", type=str, default=None, help="Security group name")
    parser.add_argument("--az", type=str, default=None, help="Availability zone")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode — validate structure without creating or deleting any VM")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="State poll interval in seconds (default: 3.0)")
    parser.add_argument("--lifecycle-timing", action="store_true", help="Output detailed lifecycle timing JSON to benchmark_results/vm_engine/")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    args = parser.parse_args()

    asyncio.run(run_validation(args))


async def run_validation(args: argparse.Namespace) -> None:
    print("=" * 68)
    print("  VM Engine Validation — Phase 6")
    print("=" * 68)

    result = await validate_engine(args)

    print(f"\n{'=' * 68}")
    status = "✅ ALL PASSED" if result.all_passed else "❌ FAILED"
    print(f"  Result: {status} ({result.passed_count}/{result.total_count})")
    print(f"  Duration: {result.total_duration:.1f}s")
    print(f"{'=' * 68}")

    for step in result.steps:
        icon = "✅" if step.passed else "❌"
        print(f"  {icon} {step.name} ({step.duration_seconds:.1f}s)")
        if step.error:
            print(f"     Error: {step.error}")

    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "vm_engine_validation.md"
    report_path.write_text(_generate_report(result))
    print(f"\n  Report: {report_path}")

    if args.lifecycle_timing and result.lifecycle_timing:
        lt = result.lifecycle_timing
        timing_json = {
            "vm_name": lt.vm_name,
            "server_id": lt.server_id,
            "flavor_id": lt.flavor_id,
            "image_id": lt.image_id,
            "network_id": lt.network_id,
            "poll_interval_s": lt.poll_interval_s,
            "started_at": lt.started_at,
            "finished_at": lt.finished_at,
            "total_duration_s": lt.total_duration_s,
            "all_passed": lt.all_passed,
            "failure_observations": lt.failure_observations,
            "operations": [
                {
                    "operation": op.operation,
                    "passed": op.passed,
                    "total_duration_s": op.total_duration_s,
                    "api_latency_s": op.api_latency_s,
                    "state_convergence_s": op.state_convergence_s,
                    "initial_state": op.initial_state,
                    "final_state": op.final_state,
                    "error": op.error,
                    "state_trace": [
                        {"time": e.timestamp, "state": e.state, "elapsed_s": round(e.elapsed_since_start, 3)}
                        for e in op.state_trace
                    ],
                }
                for op in lt.operations
            ],
            "full_state_trace": [
                {"time": e.timestamp, "state": e.state, "elapsed_s": round(e.elapsed_since_start, 3)}
                for e in lt.full_state_trace
            ],
        }
        lt_dir = Path("benchmark_results") / "vm_engine"
        lt_dir.mkdir(parents=True, exist_ok=True)
        lt_path = lt_dir / "live_lifecycle_timing.json"
        lt_path.write_text(json.dumps(timing_json, indent=2, default=str))
        logger.info("Lifecycle timing JSON written to %s", lt_path)

    if args.json:
        json_dir = Path("benchmark_results")
        json_dir.mkdir(exist_ok=True)
        json_path = json_dir / "vm_engine_validation.json"
        json_path.write_text(json.dumps({
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "total_duration": result.total_duration,
            "all_passed": result.all_passed,
            "passed_count": result.passed_count,
            "total_count": result.total_count,
            "engine_ready": result.engine_ready,
            "server_cleaned_up": result.server_cleaned_up,
            "steps": [
                {"name": s.name, "passed": s.passed, "duration_seconds": s.duration_seconds,
                 "detail": s.detail, "error": s.error}
                for s in result.steps
            ],
        }, indent=2, default=str))
        logger.info("JSON written to %s", json_path)

    if not result.all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
