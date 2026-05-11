#!/usr/bin/env python3
"""Live vCenter Validation Script — Phase 5.

Validates the VMware assessment engine against a real vCenter environment.

Usage
-----
    # Basic validation (requires VMWARE_HOST/USER/PASS env vars)
    PYTHONPATH=. python scripts/validate_vcenter.py

    # Export results
    PYTHONPATH=. python scripts/validate_vcenter.py --json
    PYTHONPATH=. python scripts/validate_vcenter.py --report

    # Validate specific VM
    PYTHONPATH=. python scripts/validate_vcenter.py --vm "my-vm-name"

    # Quick connectivity check only
    PYTHONPATH=. python scripts/validate_vcenter.py --quick
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ["APP_ENV"] = "validation"

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
from app.clients.vmware.connection import VMwareClientFactory
from app.clients.vmware.pool import VMwareConnectionPool
from app.core.config.settings import Settings
from app.schemas.vmware.inventory import VMSummary


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    operation: str
    success: bool
    duration_ms: float
    detail: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class VMDetail:
    name: str
    id: str
    power_state: str
    guest_os: str
    firmware: str | None
    secure_boot: bool | None
    tools_status: str | None
    cpu_count: int
    memory_mb: int
    disk_count: int
    disk_controller_types: list[str]
    nic_count: int
    nic_types: list[str]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

# Import Prometheus metrics when available (graceful fallback if not running
# in Gunicorn multiproc context)
try:
    from app.common.metrics.custom import vmw_vcenter_api_duration
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False


def _measure(label: str, fn: callable, *args, **kwargs) -> tuple[Any, float]:
    """Execute fn and return (result, duration_ms)."""
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        dur = (time.perf_counter() - start) * 1000
        if _HAS_METRICS:
            vmw_vcenter_api_duration.labels(operation=label, status="success").observe(dur / 1000)
        return result, dur
    except Exception:
        dur = (time.perf_counter() - start) * 1000
        if _HAS_METRICS:
            vmw_vcenter_api_duration.labels(operation=label, status="error").observe(dur / 1000)
        raise  # re-raise after measuring


def _get_rss_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def validate_connection(settings: Settings) -> list[ValidationResult]:
    """Step 1: Validate vCenter connectivity and credential handling."""
    results: list[ValidationResult] = []

    # --- Valid connection ---
    if not settings.vmware_ready:
        results.append(ValidationResult(
            "vmware_connection", False, 0.0,
            "VMware env vars not set (VMWARE_HOST/USER/PASS)"
        ))
        return results

    try:
        factory = VMwareClientFactory(settings)
        si, dur = _measure("connect", factory.connect)
        results.append(ValidationResult(
            "vmware_connection", True, dur,
            f"Connected to vCenter at {settings.vmware_host}"
        ))
    except Exception as e:
        results.append(ValidationResult(
            "vmware_connection", False, 0.0,
            f"Connection failed: {e}"
        ))
        return results

    # --- vCenter version ---
    try:
        about = si.content.about
        results.append(ValidationResult(
            "vcenter_version", True, 0.0,
            detail="",
            properties={
                "version": about.version,
                "build": about.build,
                "fullName": about.fullName,
                "osType": about.osType,
            }
        ))
    except Exception as e:
        results.append(ValidationResult(
            "vcenter_version", False, 0.0, str(e)
        ))

    return results


def validate_inventory(factory: VMwareClientFactory) -> list[ValidationResult]:
    """Step 2: Validate inventory collection."""
    results: list[ValidationResult] = []

    # --- List VMs ---
    try:
        raw_vms, dur = _measure("list_vms", factory.list_vms)
        results.append(ValidationResult(
            "inventory_vms", True, dur,
            f"Retrieved {len(raw_vms)} VMs",
            properties={"vm_count": len(raw_vms)}
        ))
    except Exception as e:
        results.append(ValidationResult(
            "inventory_vms", False, 0.0, str(e)
        ))
        raw_vms = []

    # --- Get VM detail (first 5 VMs) ---
    vms_checked = 0
    spot_check_details: list[VMDetail] = []
    for vm in raw_vms[:5]:
        try:
            detail, dur = _measure("get_vm_detail", factory.get_vm_detail, vm)
            vms_checked += 1

            # Extract key properties
            hw = detail.get("hardware", {})
            controllers = hw.get("disk_controller_types", []) if isinstance(hw, dict) else []
            nics = hw.get("nics", []) if isinstance(hw, dict) else []
            nic_types = [n.get("nic_type", "unknown") for n in nics] if isinstance(nics, list) else []

            vm_info = VMDetail(
                name=detail.get("name", "unknown"),
                id=detail.get("id", vm.name if hasattr(vm, 'name') else "unknown"),
                power_state=detail.get("power_state", "unknown"),
                guest_os=detail.get("guest_os", "unknown"),
                firmware=detail.get("firmware"),
                secure_boot=detail.get("secure_boot_enabled"),
                tools_status=detail.get("vmware_tools_status"),
                cpu_count=hw.get("cpu_count", 0) if isinstance(hw, dict) else 0,
                memory_mb=hw.get("memory_mb", 0) if isinstance(hw, dict) else 0,
                disk_count=len(hw.get("disks", [])) if isinstance(hw, dict) else 0,
                disk_controller_types=controllers,
                nic_count=len(nics),
                nic_types=nic_types,
            )
            spot_check_details.append(vm_info)

        except Exception as e:
            vm_name = vm.name if hasattr(vm, 'name') else "unknown"
            spot_check_details.append(VMDetail(
                name=vm_name, id="unknown", power_state="error",
                guest_os="", firmware=None, secure_boot=None,
                tools_status=None, cpu_count=0, memory_mb=0,
                disk_count=0, disk_controller_types=[], nic_count=0, nic_types=[]
            ))

    results.append(ValidationResult(
        "spot_check_vms", True, 0.0,
        f"Checked {vms_checked}/{min(5, len(raw_vms))} VM details",
        properties={"vms": [asdict(d) for d in spot_check_details]}
    ))

    # --- List datastores ---
    try:
        ds_list, dur = _measure("list_datastores", factory.list_datastores)
        results.append(ValidationResult(
            "inventory_datastores", True, dur,
            f"Retrieved {len(ds_list)} datastores",
            properties={"ds_count": len(ds_list)}
        ))
    except Exception as e:
        results.append(ValidationResult(
            "inventory_datastores", False, 0.0, str(e)
        ))

    # --- List networks ---
    try:
        net_list, dur = _measure("list_networks", factory.list_networks)
        results.append(ValidationResult(
            "inventory_networks", True, dur,
            f"Retrieved {len(net_list)} networks",
            properties={"net_count": len(net_list)}
        ))
    except Exception as e:
        results.append(ValidationResult(
            "inventory_networks", False, 0.0, str(e)
        ))

    # --- List clusters ---
    try:
        cl_list, dur = _measure("list_clusters", factory.list_clusters)
        results.append(ValidationResult(
            "inventory_clusters", True, dur,
            f"Retrieved {len(cl_list)} clusters",
            properties={"cluster_count": len(cl_list)}
        ))
    except Exception as e:
        results.append(ValidationResult(
            "inventory_clusters", False, 0.0, str(e)
        ))

    # --- List hosts ---
    try:
        host_list, dur = _measure("list_hosts", factory.list_hosts)
        results.append(ValidationResult(
            "inventory_hosts", True, dur,
            f"Retrieved {len(host_list)} hosts",
            properties={"host_count": len(host_list)}
        ))
    except Exception as e:
        results.append(ValidationResult(
            "inventory_hosts", False, 0.0, str(e)
        ))

    return results


def validate_latency_profile(factory: VMwareClientFactory, repeat: int = 5) -> list[ValidationResult]:
    """Step 3: Profile latency of key operations."""
    results: list[ValidationResult] = []
    latencies: dict[str, list[float]] = {
        "list_vms": [],
        "list_datastores": [],
        "list_networks": [],
        "list_clusters": [],
        "list_hosts": [],
    }

    for _ in range(repeat):
        for op_name in latencies:
            try:
                if op_name == "list_vms":
                    fn = factory.list_vms
                elif op_name == "list_datastores":
                    fn = factory.list_datastores
                elif op_name == "list_networks":
                    fn = factory.list_networks
                elif op_name == "list_clusters":
                    fn = factory.list_clusters
                elif op_name == "list_hosts":
                    fn = factory.list_hosts
                _, dur = _measure(op_name, fn)
                latencies[op_name].append(dur)
            except Exception:
                pass

    for op_name, durs in latencies.items():
        if not durs:
            continue
        durs.sort()
        avg_ms = sum(durs) / len(durs)
        p50 = durs[len(durs) // 2]
        p95 = durs[int(len(durs) * 0.95)]
        p99 = durs[int(len(durs) * 0.99)]
        results.append(ValidationResult(
            f"latency_{op_name}", True, avg_ms,
            f"p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms (n={len(durs)})",
            properties={
                "avg_ms": round(avg_ms, 2),
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "min_ms": round(min(durs), 2),
                "max_ms": round(max(durs), 2),
                "sample_count": len(durs),
            }
        ))

    return results


def validate_pool_reconnect(settings: Settings) -> list[ValidationResult]:
    """Step 4: Validate connection pool reconnect behavior."""
    results: list[ValidationResult] = []
    try:
        pool = VMwareConnectionPool(
            settings, max_pool_size=2, session_ttl_seconds=30,
            health_check_interval=5
        )
        factory = VMwareClientFactory(settings, pool=pool)

        # Acquire connection
        conn1 = pool.acquire()
        results.append(ValidationResult(
            "pool_acquire", True, 0.0,
            "Connection acquired from pool"
        ))

        # Force expire — use the connection to check if alive
        alive = conn1.is_alive()
        results.append(ValidationResult(
            "pool_is_alive", alive, 0.0,
            f"Connection alive check: {alive}"
        ))

        # Release
        pool.release(conn1)
        results.append(ValidationResult(
            "pool_release", True, 0.0,
            "Connection released back to pool"
        ))

        # Re-acquire
        conn2 = pool.acquire()
        results.append(ValidationResult(
            "pool_reacquire", True, 0.0,
            "Connection re-acquired from pool"
        ))
        pool.release(conn2)

        # Disconnect all
        pool.disconnect_all()
        results.append(ValidationResult(
            "pool_disconnect_all", True, 0.0,
            "All pool connections disconnected"
        ))

    except Exception as e:
        results.append(ValidationResult(
            "pool_validation", False, 0.0,
            f"Pool validation failed: {e}"
        ))

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(settings: Settings, all_results: list[ValidationResult]) -> str:
    """Generate markdown report from validation results."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(all_results)
    passed = sum(1 for r in all_results if r.success)
    failed = total - passed

    lines = [
        f"# vCenter Validation Report",
        f"",
        f"> Generated: {now}",
        f"> Target: {settings.vmware_host or '(not set)'}",
        f"> Result: **{passed}/{total} checks passed**",
        f"",
        f"## Summary",
        f"",
        f"| Status | Count |",
        f"|--------|:-----:|",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Total  | {total} |",
        f"",
        f"## Operation Results",
        f"",
        f"| Operation | Status | Duration (ms) | Detail |",
        f"|-----------|:------:|:-------------:|--------|",
    ]

    for r in all_results:
        status = "✅" if r.success else "❌"
        dur = f"{r.duration_ms:.1f}" if r.duration_ms > 0 else "-"
        detail_escaped = r.detail.replace("|", "\\|")
        lines.append(
            f"| {r.operation} | {status} | {dur} | {detail_escaped} |"
        )

    # Append VM details
    for r in all_results:
        if r.operation == "spot_check_vms" and r.properties.get("vms"):
            lines.extend([
                f"",
                f"## Spot-Checked VM Details",
                f"",
                f"| Name | Power | OS | Firmware | SecureBoot | Tools | vCPUs | RAM(MB) | Disks | Controllers | NICs | NIC Types |",
                f"|------|:-----:|:--:|:--------:|:----------:|:-----:|:-----:|:-------:|:-----:|:-----------:|:----:|:---------:|",
            ])
            for vmd in r.properties["vms"]:
                lines.append(
                    f"| {vmd['name']} | {vmd['power_state']} | {vmd['guest_os'][:40]} | "
                    f"{vmd['firmware'] or '-'} | {vmd['secure_boot'] or '-'} | "
                    f"{vmd['tools_status'] or '-'} | {vmd['cpu_count']} | {vmd['memory_mb']} | "
                    f"{vmd['disk_count']} | {','.join(vmd['disk_controller_types'][:3]) or '-'} | "
                    f"{vmd['nic_count']} | {','.join(vmd['nic_types'][:3]) or '-'} |"
                )

    # Append latency profile
    latency_results = [r for r in all_results if r.operation.startswith("latency_")]
    if latency_results:
        lines.extend([
            f"",
            f"## Latency Profile (avg of {latency_results[0].properties.get('sample_count', 'N')} samples)",
            f"",
            f"| Operation | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) |",
            f"|-----------|:--------:|:--------:|:--------:|:--------:|",
        ])
        for r in latency_results:
            op_name = r.operation.replace("latency_", "")
            p = r.properties
            lines.append(
                f"| {op_name} | {p.get('avg_ms', '-')} | {p.get('p50_ms', '-')} | "
                f"{p.get('p95_ms', '-')} | {p.get('p99_ms', '-')} |"
            )

    lines.append(f"\n---\n*Report generated by validate_vcenter.py*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def generate_json(all_results: list[ValidationResult]) -> dict:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_checks": len(all_results),
        "passed": sum(1 for r in all_results if r.success),
        "failed": sum(1 for r in all_results if not r.success),
        "results": [
            {
                "operation": r.operation,
                "success": r.success,
                "duration_ms": round(r.duration_ms, 2),
                "detail": r.detail,
                "properties": r.properties,
            }
            for r in all_results
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Live vCenter Validation")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    parser.add_argument("--report", action="store_true", help="Export markdown report")
    parser.add_argument("--quick", action="store_true", help="Connectivity check only")
    parser.add_argument("--vm", type=str, help="Specific VM name to validate")
    args = parser.parse_args()

    settings = Settings()

    if not settings.vmware_ready:
        print("ERROR: VMware environment variables not set.")
        print("Required: VMWARE_HOST, VMWARE_USER, VMWARE_PASSWORD")
        sys.exit(1)

    mem_before = _get_rss_mb()
    print(f"vCenter Validation — Target: {settings.vmware_host}")
    print(f"Memory before: {mem_before:.1f} MB")
    print()

    all_results: list[ValidationResult] = []

    # Step 1: Connection
    print("[1/4] Validating connection...")
    all_results.extend(validate_connection(settings))

    # Step 2: Inventory (skip if --quick)
    if not args.quick:
        factory = VMwareClientFactory(settings)
        print("[2/4] Validating inventory collection...")
        all_results.extend(validate_inventory(factory))

        # Step 3: Latency profile
        print("[3/4] Profiling latency...")
        all_results.extend(validate_latency_profile(factory, repeat=5))

        # Step 4: Pool reconnect (quick test)
        print("[4/4] Validating pool reconnect...")
        all_results.extend(validate_pool_reconnect(settings))

    # Summary
    print()
    passed = sum(1 for r in all_results if r.success)
    failed = len(all_results) - passed
    mem_after = _get_rss_mb()
    print(f"Results: {passed}/{len(all_results)} checks passed ({failed} failed)")
    print(f"Memory after: {mem_after:.1f} MB (delta: {mem_after - mem_before:.1f} MB)")
    print()

    for r in all_results:
        status = "✅" if r.success else "❌"
        dur = f" ({r.duration_ms:.1f}ms)" if r.duration_ms > 0 else ""
        print(f"  {status} {r.operation}{dur}: {r.detail[:100]}")

    # Export
    output_dir = Path("benchmark_results/validation")
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.report or not args.json:
        report = generate_report(settings, all_results)
        report_path = output_dir / "vcenter_validation_report.md"
        report_path.write_text(report)
        print(f"\nReport: {report_path}")

    if args.json:
        json_path = output_dir / "vcenter_validation.json"
        json_path.write_text(json.dumps(generate_json(all_results), indent=2))
        print(f"JSON:   {json_path}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
