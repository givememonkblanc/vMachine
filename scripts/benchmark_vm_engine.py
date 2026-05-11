#!/usr/bin/env python3
"""VM Engine Benchmark Harness — Phase 6.

Measures VM create/delete throughput and lifecycle operation latency
against a real OpenStack Nova deployment.

Benchmark cases:
  1. Create + delete 1 VM (cold start)
  2. Create + delete 3 VMs sequentially (sequential throughput)
  3. Lifecycle on 1 VM: create → reboot → stop → start → delete

Usage:
    PYTHONPATH=. python scripts/benchmark_vm_engine.py
    PYTHONPATH=. python scripts/benchmark_vm_engine.py --json
    PYTHONPATH=. python scripts/benchmark_vm_engine.py --flavor m1.tiny --image cirros --network private

Output:
    benchmark_results/vm_engine/benchmark.json     (machine-readable)
    docs/vm_engine_benchmark_report.md              (human-readable)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.core.config.settings import get_settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("benchmark_vm_engine")


@dataclass
class BenchmarkCase:
    name: str
    passed: bool = False
    duration_seconds: float = 0.0
    create_duration: float = 0.0
    delete_duration: float = 0.0
    operation_durations: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    cleanup_ok: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    started_at: str = ""
    finished_at: str = ""
    total_duration: float = 0.0
    cases: list[BenchmarkCase] = field(default_factory=list)
    all_passed: bool = False

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.cases)


async def run_benchmark(args: argparse.Namespace) -> BenchmarkResult:
    result = BenchmarkResult(
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    settings = get_settings()
    if not settings.openstack_ready:
        logger.error("OpenStack not configured — skipping live benchmarks")
        result.all_passed = False
        result.finished_at = datetime.now(timezone.utc).isoformat()
        result.cases.append(
            BenchmarkCase(
                name="all_cases_skipped",
                passed=False,
                errors=[
                    "OpenStack not configured — set OPENSTACK_AUTH_URL/USERNAME/PASSWORD/etc."
                ],
            )
        )
        return result

    from app.schemas.openstack.vm_lifecycle import VMCreateRequest
    from app.services.openstack.vm_provisioning_engine import VMProvisioningEngine

    factory = OpenStackConnectionFactory(settings)
    engine = VMProvisioningEngine(factory)

    try:
        flavors = list(await engine._nova_call("flavors", 30.0, get_all=True))
        images = await engine._nova_call("images", 30.0)
        networks_list = await factory.call("network", "networks")
    except Exception as exc:
        logger.error("Cannot connect to OpenStack: %s", exc)
        result.all_passed = False
        result.finished_at = datetime.now(timezone.utc).isoformat()
        result.cases.append(
            BenchmarkCase(
                name="resource_discovery",
                passed=False,
                errors=[f"OpenStack connection failed: {exc}"],
            )
        )
        return result

    flavor_id = args.flavor or (flavors[0].id if flavors else None)
    image_id = args.image or (images[0].id if images else None)
    network_id = args.network or (networks_list[0].id if networks_list else None)

    if not flavor_id or not image_id or not network_id:
        logger.error("Cannot discover required OpenStack resources")
        result.all_passed = False
        result.finished_at = datetime.now(timezone.utc).isoformat()
        result.cases.append(
            BenchmarkCase(
                name="resource_discovery",
                passed=False,
                errors=["Failed to discover flavor/image/network"],
            )
        )
        return result

    logger.info("Using flavor=%s image=%s network=%s", flavor_id, image_id, network_id)

    # ---------------------------------------------------------------
    # Case 1: Create + delete 1 VM
    # ---------------------------------------------------------------
    case1 = await _benchmark_single_vm(engine, flavor_id, image_id, network_id, args, 1)
    result.cases.append(case1)

    # ---------------------------------------------------------------
    # Case 2: Create + delete 3 VMs sequentially
    # ---------------------------------------------------------------
    case2 = BenchmarkCase(name="sequential_create_delete_3")
    t0 = time.monotonic()
    try:
        create_times = []
        delete_times = []
        all_clean = True
        for i in range(3):
            sub = await _benchmark_single_vm(
                engine, flavor_id, image_id, network_id, args, idx=i + 1
            )
            create_times.append(sub.create_duration)
            delete_times.append(sub.delete_duration)
            if not sub.cleanup_ok:
                all_clean = False
        case2.create_duration = sum(create_times) / len(create_times)
        case2.delete_duration = sum(delete_times) / len(delete_times)
        case2.detail = {
            "individual_create_times": create_times,
            "individual_delete_times": delete_times,
            "avg_create_s": round(sum(create_times) / len(create_times), 2),
            "avg_delete_s": round(sum(delete_times) / len(delete_times), 2),
            "total_vms_created": 3,
        }
        case2.cleanup_ok = all_clean
        case2.passed = True
        logger.info(
            "Case 2: 3 sequential VMs — create avg=%.2fs delete avg=%.2fs",
            sum(create_times) / len(create_times),
            sum(delete_times) / len(delete_times),
        )
    except Exception as exc:
        case2.errors.append(str(exc))
        case2.passed = False
    case2.duration_seconds = time.monotonic() - t0
    result.cases.append(case2)

    # ---------------------------------------------------------------
    # Case 3: Lifecycle on 1 VM (create → reboot → stop → start → delete)
    # ---------------------------------------------------------------
    case3 = BenchmarkCase(name="vm_lifecycle_operations")
    t0 = time.monotonic()
    vm_name = f"vmachine-test-bench-lifecycle-{int(time.time())}"
    server_id = None
    try:
        req = VMCreateRequest(
            name=vm_name,
            flavor_id=flavor_id,
            image_id=image_id,
            network_ids=[network_id],
        )
        vm = await engine.create_vm(req)
        server_id = vm.id
        case3.create_duration = time.monotonic() - t0

        tr = time.monotonic()
        await engine.reboot_vm(server_id)
        case3.operation_durations["reboot"] = time.monotonic() - tr

        ts = time.monotonic()
        await engine.stop_vm(server_id)
        case3.operation_durations["stop"] = time.monotonic() - ts

        tst = time.monotonic()
        await engine.start_vm(server_id)
        case3.operation_durations["start"] = time.monotonic() - tst

        td = time.monotonic()
        await engine.delete_vm(server_id)
        case3.operation_durations["delete"] = time.monotonic() - td

        try:
            await engine.get_vm(server_id)
            case3.errors.append("Server still exists after deletion")
            case3.cleanup_ok = False
        except Exception:
            case3.cleanup_ok = True

        case3.detail = {
            "vm_name": vm_name,
            "server_id": server_id,
            "operations": {
                "create_s": round(case3.create_duration, 2),
                **{k: round(v, 2) for k, v in case3.operation_durations.items()},
            },
        }
        case3.passed = True
        logger.info("Case 3: lifecycle on VM %s — all ops passed", server_id)
    except Exception as exc:
        case3.errors.append(str(exc))
        case3.passed = False
    finally:
        if server_id and not case3.cleanup_ok:
            try:
                await engine.delete_vm(server_id)
            except Exception:
                pass
    case3.duration_seconds = time.monotonic() - t0
    result.cases.append(case3)

    result.all_passed = all(c.passed for c in result.cases)
    result.finished_at = datetime.now(timezone.utc).isoformat()
    if result.cases:
        result.total_duration = (
            datetime.fromisoformat(result.finished_at)
            - datetime.fromisoformat(result.started_at)
        ).total_seconds()
    return result


async def _benchmark_single_vm(
    engine,
    flavor_id: str,
    image_id: str,
    network_id: str,
    args: argparse.Namespace,
    idx: int = 0,
) -> BenchmarkCase:
    case = BenchmarkCase(name=f"single_create_delete_{idx}")
    t0 = time.monotonic()
    vm_name = f"vmachine-test-bench-{idx}-{int(time.time())}"
    server_id = None
    try:
        from app.schemas.openstack.vm_lifecycle import VMCreateRequest

        req = VMCreateRequest(
            name=vm_name,
            flavor_id=flavor_id,
            image_id=image_id,
            network_ids=[network_id],
        )
        vm = await engine.create_vm(req)
        server_id = vm.id
        case.create_duration = time.monotonic() - t0
        logger.info("Created VM %s (%.2fs)", server_id, case.create_duration)

        td = time.monotonic()
        await engine.delete_vm(server_id)
        case.delete_duration = time.monotonic() - td
        logger.info("Deleted VM %s (%.2fs)", server_id, case.delete_duration)

        case.cleanup_ok = True
        case.passed = True
        case.detail = {
            "vm_name": vm_name,
            "server_id": server_id,
            "create_s": round(case.create_duration, 2),
            "delete_s": round(case.delete_duration, 2),
        }
    except Exception as exc:
        case.errors.append(str(exc))
        case.passed = False
    finally:
        if server_id and not case.cleanup_ok:
            try:
                await engine.delete_vm(server_id)
                case.cleanup_ok = True
            except Exception:
                pass
    case.duration_seconds = time.monotonic() - t0
    return case


def _generate_report(result: BenchmarkResult) -> str:
    lines = [
        "# VM Engine Benchmark Report",
        "",
        f"> Started: {result.started_at}",
        f"> Finished: {result.finished_at}",
        f"> Duration: {result.total_duration:.1f}s",
        f"> Result: **{'✅ ALL PASSED' if result.all_passed else '❌ FAILED'}** ({result.passed_count}/{result.total_count})",
        "",
        "## Summary",
        "",
        "| Case | Status | Duration | Detail |",
        "|------|:------:|:--------:|--------|",
    ]
    for case in result.cases:
        status = "✅" if case.passed else "❌"
        dur = f"{case.duration_seconds:.1f}s"
        if case.errors:
            detail = case.errors[0][:100]
        elif case.detail:
            detail = str(case.detail)[:100]
        else:
            detail = ""
        detail = detail.replace("|", "\\|")
        lines.append(f"| {case.name} | {status} | {dur} | {detail} |")

    lines.extend(["", "## Case Details", ""])
    for case in result.cases:
        lines.append(f"### {case.name}")
        lines.append("")
        lines.append(f"- **Passed**: {case.passed}")
        lines.append(f"- **Duration**: {case.duration_seconds:.2f}s")
        if case.create_duration:
            lines.append(f"- **Create**: {case.create_duration:.2f}s")
        if case.delete_duration:
            lines.append(f"- **Delete**: {case.delete_duration:.2f}s")
        if case.operation_durations:
            for op, dur in case.operation_durations.items():
                lines.append(f"- **{op}**: {dur:.2f}s")
        if case.errors:
            for err in case.errors:
                lines.append(f"- **Error**: {err}")
        if case.detail:
            for k, v in case.detail.items():
                if not isinstance(v, dict | list):
                    lines.append(f"- **{k}**: {v}")
        lines.append(f"- **Cleanup OK**: {case.cleanup_ok}")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by benchmark_vm_engine.py*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="VM Engine Benchmark Harness")
    parser.add_argument(
        "--flavor",
        type=str,
        default=None,
        help="Flavor ID/name (default: first available)",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Image ID/name (default: first available)",
    )
    parser.add_argument(
        "--network",
        type=str,
        default=None,
        help="Network ID (default: first available)",
    )
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    args = parser.parse_args()

    result = asyncio.run(run_benchmark(args))

    print("=" * 68)
    print("  VM Engine Benchmark — Phase 6")
    print("=" * 68)
    status = "✅ ALL PASSED" if result.all_passed else "❌ FAILED"
    print(f"  Result: {status} ({result.passed_count}/{result.total_count})")
    print(f"  Duration: {result.total_duration:.1f}s")
    print("=" * 68)

    for case in result.cases:
        icon = "✅" if case.passed else "❌"
        print(f"  {icon} {case.name} ({case.duration_seconds:.1f}s)")
        if case.errors:
            for err in case.errors:
                print(f"     Error: {err}")

    # Outputs
    output_dir = Path("benchmark_results/vm_engine")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = Path("docs") / "vm_engine_benchmark_report.md"
    report_path.write_text(_generate_report(result))
    print(f"\n  Report: {report_path}")

    if args.json:
        json_path = output_dir / "benchmark.json"
        json_path.write_text(
            json.dumps(
                {
                    "started_at": result.started_at,
                    "finished_at": result.finished_at,
                    "total_duration": result.total_duration,
                    "all_passed": result.all_passed,
                    "passed_count": result.passed_count,
                    "total_count": result.total_count,
                    "cases": [
                        {
                            "name": c.name,
                            "passed": c.passed,
                            "duration_seconds": c.duration_seconds,
                            "create_duration": c.create_duration,
                            "delete_duration": c.delete_duration,
                            "operation_durations": c.operation_durations,
                            "errors": c.errors,
                            "cleanup_ok": c.cleanup_ok,
                            "detail": c.detail,
                        }
                        for c in result.cases
                    ],
                },
                indent=2,
                default=str,
            )
        )
        logger.info("JSON written to %s", json_path)

    if not result.all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
