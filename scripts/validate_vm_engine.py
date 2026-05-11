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

    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.steps if s.passed)

    @property
    def total_count(self) -> int:
        return len(self.steps)


async def validate_engine(args: argparse.Namespace) -> ValidationResult:
    result = ValidationResult(
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    factory = OpenStackConnectionFactory(get_settings())

    if not get_settings().openstack_ready:
        logger.error("OpenStack not configured — set OPENSTACK_AUTH_URL/USERNAME/PASSWORD/etc.")
        result.steps.append(ValidationStep(
            name="engine_ready", passed=False,
            error="OpenStack env vars not set",
        ))
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

    try:
        # ---------------------------------------------------------------
        # 1. List flavors, images, networks
        # ---------------------------------------------------------------
        step = ValidationStep(name="discover_resources")
        t0 = time.monotonic()
        try:
            flavors = list(await engine._nova_call("flavors", 30.0, get_all=True))
            step.detail["flavor_count"] = len(flavors)
            logger.info("Found %d flavors", len(flavors))

            images = await engine._nova_call("images", 30.0)
            step.detail["image_count"] = len(images)
            logger.info("Found %d images", len(images))

            networks_list = await factory.call("network", "networks")
            step.detail["network_count"] = len(networks_list)
            logger.info("Found %d networks", len(networks_list))

            flavor_id = args.flavor or (flavors[0].id if flavors else None)
            image_id = args.image or (images[0].id if images else None)
            network_id = args.network or (networks_list[0].id if networks_list else None)

            if not flavor_id or not image_id or not network_id:
                raise RuntimeError(f"Missing resources: flavor={flavor_id} image={image_id} network={network_id}")

            step.detail["selected"] = {
                "flavor_id": flavor_id,
                "image_id": image_id,
                "network_id": network_id,
            }
            step.passed = True
            logger.info("Selected flavor=%s image=%s network=%s", flavor_id, image_id, network_id)
        except Exception as exc:
            step.error = str(exc)
            step.passed = False
            logger.error("Resource discovery failed: %s", exc)
        step.duration_seconds = time.monotonic() - t0
        result.steps.append(step)

        if not step.passed:
            result.all_passed = False
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        # ---------------------------------------------------------------
        # 2. Create VM
        # ---------------------------------------------------------------
        step = ValidationStep(name="create_vm")
        t0 = time.monotonic()
        try:
            req = VMCreateRequest(
                name=args.vm_name or f"validate-{int(t0)}",
                flavor_id=flavor_id,
                image_id=image_id,
                network_ids=[network_id],
                keypair=args.keypair or None,
                security_groups=[args.security_group] if args.security_group else None,
                availability_zone=args.az or None,
            )
            vm = await engine.create_vm(req)
            created_server_id = vm.id
            step.detail = {
                "server_id": vm.id,
                "name": vm.name,
                "status": vm.status,
                "flavor_id": vm.flavor_id,
                "image_id": vm.image_id,
            }
            step.passed = vm.status == "ACTIVE"
            logger.info("VM created id=%s status=%s", vm.id, vm.status)
        except Exception as exc:
            step.error = str(exc)
            step.passed = False
            logger.error("VM creation failed: %s", exc)
        step.duration_seconds = time.monotonic() - t0
        result.steps.append(step)

        if not step.passed:
            result.all_passed = False
            if created_server_id:
                await _cleanup(engine, created_server_id)
                cleanup_attempted = True
            result.server_cleaned_up = cleanup_attempted
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        # ---------------------------------------------------------------
        # 3. Reboot VM
        # ---------------------------------------------------------------
        resp = await _run_lifecycle_step(engine, "reboot", created_server_id)
        result.steps.append(resp)

        # ---------------------------------------------------------------
        # 4. Stop VM
        # ---------------------------------------------------------------
        stop_resp = await _run_lifecycle_step(engine, "stop", created_server_id)
        result.steps.append(stop_resp)

        # ---------------------------------------------------------------
        # 5. Start VM
        # ---------------------------------------------------------------
        start_resp = await _run_lifecycle_step(engine, "start", created_server_id)
        result.steps.append(start_resp)

        # ---------------------------------------------------------------
        # 6. Delete VM
        # ---------------------------------------------------------------
        step = ValidationStep(name="delete_vm")
        t0 = time.monotonic()
        try:
            del_resp = await engine.delete_vm(created_server_id)
            step.detail = {"server_id": created_server_id, "status": del_resp.status}
            step.passed = True
            logger.info("VM deleted id=%s", created_server_id)
        except Exception as exc:
            step.error = str(exc)
            step.passed = False
            logger.error("VM deletion failed: %s", exc)
        step.duration_seconds = time.monotonic() - t0
        result.steps.append(step)

        # ---------------------------------------------------------------
        # 7. Verify cleanup (server should 404)
        # ---------------------------------------------------------------
        step = ValidationStep(name="verify_cleanup")
        t0 = time.monotonic()
        try:
            await engine.get_vm(created_server_id)
            step.passed = False
            step.error = "Server still exists after deletion"
            logger.error("Server %s still exists after deletion!", created_server_id)
        except Exception as exc:
            error_str = str(exc)
            if "not found" in error_str.lower() or "404" in error_str:
                step.passed = True
                step.detail = {"confirmed": "server no longer exists"}
                logger.info("Cleanup verified — server %s gone", created_server_id)
            else:
                step.passed = False
                step.error = error_str
        step.duration_seconds = time.monotonic() - t0
        result.steps.append(step)

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
        result.total_duration = (datetime.fromisoformat(result.finished_at) - datetime.fromisoformat(result.started_at)).total_seconds()
    return result


async def _run_lifecycle_step(engine: VMProvisioningEngine, operation: str, server_id: str) -> ValidationStep:
    step = ValidationStep(name=f"vm_{operation}")
    t0 = time.monotonic()
    try:
        method = getattr(engine, f"{operation}_vm")
        resp = await method(server_id)
        step.detail = {"server_id": server_id, "status": resp.status, "elapsed": round(resp.elapsed_seconds, 2)}
        step.passed = resp.status == "success"
        logger.info("VM %s %s (%.1fs)", server_id, operation, resp.elapsed_seconds)
    except Exception as exc:
        step.error = str(exc)
        step.passed = False
        logger.error("VM %s %s failed: %s", server_id, operation, exc)
    step.duration_seconds = time.monotonic() - t0
    return step


async def _cleanup(engine: VMProvisioningEngine, server_id: str) -> None:
    try:
        await engine.delete_vm(server_id)
        logger.info("Cleanup: deleted server id=%s", server_id)
    except Exception as exc:
        logger.warning("Cleanup failed for server id=%s: %s", server_id, exc)


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
