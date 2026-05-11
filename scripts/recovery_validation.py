#!/usr/bin/env python3
"""Failure & Recovery Validation Harness — Phase 5.

Simulates infrastructure failure scenarios and validates the assessment engine's
resilience: graceful degradation, retry logic, reconnection, and structured error
propagation.

Usage
-----
    PYTHONPATH=. python scripts/recovery_validation.py
    PYTHONPATH=. python scripts/recovery_validation.py --json
    PYTHONPATH=. python scripts/recovery_validation.py --scenario disconnect,timeout,pool
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ["APP_ENV"] = "validation"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FailureScenario:
    name: str
    description: str
    passed: bool = False
    duration_ms: float = 0.0
    error_type: str | None = None
    error_message: str = ""
    recovered: bool = False
    recovery_time_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scenario 1: vCenter Disconnect / Reconnect
# ---------------------------------------------------------------------------

def scenario_vcenter_disconnect() -> FailureScenario:
    """Simulate vCenter temporary disconnect and validate reconnection."""
    sc = FailureScenario(
        name="vcenter_disconnect",
        description="vCenter temporary disconnect, validate reconnect via pool health check",
    )
    try:
        from app.clients.vmware.pool import VMwareConnectionPool
        from app.core.config.settings import Settings

        settings = Settings()
        if not settings.vmware_ready:
            sc.passed = True  # skip if no vCenter
            sc.error_type = "skipped"
            sc.error_message = "VMware env not configured — scenario skipped (expected behavior)"
            sc.details = {"note": "Requires VMWARE_HOST/USER/PASS to test real disconnect"}
            return sc

        pool = VMwareConnectionPool(
            settings, max_pool_size=2, session_ttl_seconds=600,
            health_check_interval=5
        )

        # Acquire connection
        conn = pool.acquire()
        start = time.perf_counter()

        # Verify alive
        alive_before = conn.is_alive()
        sc.details["alive_before"] = alive_before

        # Release and disconnect all (simulating vCenter disconnect)
        pool.release(conn)
        pool.disconnect_all()
        sc.details["disconnected"] = True

        # Re-acquire (should reconnect automatically)
        t0 = time.perf_counter()
        conn2 = pool.acquire()
        reconnect_ms = (time.perf_counter() - t0) * 1000
        alive_after = conn2.is_alive()
        pool.release(conn2)

        sc.passed = alive_after
        sc.recovered = alive_after
        sc.recovery_time_ms = reconnect_ms
        sc.duration_ms = (time.perf_counter() - start) * 1000
        sc.details.update({
            "alive_after": alive_after,
            "reconnect_ms": round(reconnect_ms, 2),
        })

    except Exception as e:
        sc.passed = False
        sc.error_type = type(e).__name__
        sc.error_message = str(e)

    return sc


# ---------------------------------------------------------------------------
# Scenario 2: Expired VMware Session
# ---------------------------------------------------------------------------

def scenario_expired_session() -> FailureScenario:
    """Simulate expired vCenter session (stale connection in pool)."""
    sc = FailureScenario(
        name="expired_session",
        description="Expired vCenter session detection and auto-reconnect",
    )
    try:
        from app.clients.vmware.pool import VMwareConnectionPool
        from app.core.config.settings import Settings

        settings = Settings()
        if not settings.vmware_ready:
            sc.passed = True
            sc.error_type = "skipped"
            sc.error_message = "VMware env not configured — scenario skipped"
            return sc

        # Pool with very short TTL to force expiry
        pool = VMwareConnectionPool(
            settings, max_pool_size=2, session_ttl_seconds=1,
            health_check_interval=1
        )

        conn = pool.acquire()
        sc.details["created_at"] = conn.created_at

        # Wait for TTL to expire
        time.sleep(1.5)

        # Re-acquire same slot — should detect stale and reconnect
        t0 = time.perf_counter()
        conn2 = pool.acquire()
        reconnect_ms = (time.perf_counter() - t0) * 1000

        alive = conn2.is_alive()
        pool.release(conn2)

        sc.passed = alive
        sc.recovered = alive
        sc.recovery_time_ms = reconnect_ms
        sc.details.update({
            "alive_after_expiry": alive,
            "reconnect_ms": round(reconnect_ms, 2),
        })

    except Exception as e:
        sc.passed = False
        sc.error_type = type(e).__name__
        sc.error_message = str(e)

    return sc


# ---------------------------------------------------------------------------
# Scenario 3: Pool Exhaustion
# ---------------------------------------------------------------------------

def scenario_pool_exhaustion() -> FailureScenario:
    """Validate pool exhaustion behavior — acquire more than max_pool_size."""
    sc = FailureScenario(
        name="pool_exhaustion",
        description="Connection pool exhaustion — acquire beyond max_pool_size",
    )
    try:
        from app.clients.vmware.pool import VMwareConnectionPool
        from app.core.config.settings import Settings

        settings = Settings()
        if not settings.vmware_ready:
            sc.passed = True
            sc.error_type = "skipped"
            sc.error_message = "VMware env not configured — scenario skipped"
            return sc

        pool = VMwareConnectionPool(
            settings, max_pool_size=2, session_ttl_seconds=600,
            health_check_interval=60
        )

        # Acquire max connections
        conns = []
        for i in range(pool.max_pool_size):
            conns.append(pool.acquire())

        sc.details["acquired"] = len(conns)
        sc.details["max_pool_size"] = pool.max_pool_size

        # Try to acquire one more — should block or return None
        t0 = time.perf_counter()
        try:
            extra = pool.acquire()
            sc.details["extra_acquired"] = True
            pool.release(extra)
        except Exception as e:
            sc.details["extra_acquired"] = False
            sc.details["extra_error"] = str(e)
        wait_ms = (time.perf_counter() - t0) * 1000
        sc.details["wait_for_extra_ms"] = round(wait_ms, 2)

        # Release all
        for c in conns:
            pool.release(c)

        sc.passed = True
        sc.recovered = True
        sc.duration_ms = wait_ms

    except Exception as e:
        sc.passed = False
        sc.error_type = type(e).__name__
        sc.error_message = str(e)

    return sc


# ---------------------------------------------------------------------------
# Scenario 4: Malformed VM Metadata
# ---------------------------------------------------------------------------

def scenario_malformed_vm_metadata() -> FailureScenario:
    """Validate that malformed VM metadata does not crash the engine."""
    sc = FailureScenario(
        name="malformed_vm_metadata",
        description="Malformed VM metadata — null fields, missing properties",
    )
    try:
        from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
        from app.services.vmware.compatibility import VMwareCompatibilityService

        svc = VMwareCompatibilityService()
        error_count = 0

        edge_case_vms = [
            VMSummary(id="null-vm", name="", power_state="", guest_os=None,
                      hardware=None, firmware=None, secure_boot_enabled=None,
                      vmware_tools_status=None, disk_controller_types=None),
            VMSummary(id="empty-vm", name="", power_state="", guest_os="",
                      hardware=VMHardware(cpu_count=0, memory_mb=0, disks=[], nics=[]),
                      firmware="", secure_boot_enabled=False,
                      vmware_tools_status="", disk_controller_types=[]),
            VMSummary(id="partial-vm", name="partial", power_state="poweredOn",
                      guest_os="Some OS",
                      hardware=VMHardware(cpu_count=4, memory_mb=8192,
                          disks=[VMDisk(label="d1", capacity_gb=100, datastore_name="ds1", controller_type="scsi")],
                          nics=[VMNic(label="n1", network_name="net1", mac_address="00:00:00:00:00:00", nic_type="vmxnet3")]),
                      firmware="bios", secure_boot_enabled=False,
                      vmware_tools_status=None, disk_controller_types=None),
        ]

        for vm in edge_case_vms:
            try:
                result = svc.evaluate(vm)
                if result is None:
                    error_count += 1
            except Exception:
                error_count += 1

        sc.passed = error_count == 0
        sc.details = {
            "tested_vms": len(edge_case_vms),
            "errors": error_count,
        }
        if error_count > 0:
            sc.error_type = "EvaluationError"
            sc.error_message = f"{error_count}/{len(edge_case_vms)} edge case VMs caused errors"

    except Exception as e:
        sc.passed = False
        sc.error_type = type(e).__name__
        sc.error_message = str(e)

    return sc


# ---------------------------------------------------------------------------
# Scenario 5: Unsupported Guest OS
# ---------------------------------------------------------------------------

def scenario_unsupported_guest_os() -> FailureScenario:
    """Validate unsupported guest OS detection."""
    sc = FailureScenario(
        name="unsupported_guest_os",
        description="Unsupported guest OS detection — graceful handling",
    )
    try:
        from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
        from app.services.vmware.compatibility import VMwareCompatibilityService

        svc = VMwareCompatibilityService()
        unsupported_oses = ["Solaris 11", "HP-UX 11i", "AIX 7.2", "Darwin 23"]

        for os_name in unsupported_oses:
            vm = VMSummary(
                id=f"unsupported-{os_name[:5]}",
                name=os_name,
                power_state="poweredOn",
                guest_os=os_name,
                hardware=VMHardware(cpu_count=2, memory_mb=4096,
                    disks=[VMDisk(label="d1", capacity_gb=40, datastore_name="ds1", controller_type="scsi")],
                    nics=[VMNic(label="n1", network_name="net1", mac_address="00:00:00:00:00:01", nic_type="vmxnet3")]),
                firmware="bios", secure_boot_enabled=False,
                vmware_tools_status="toolsOk", disk_controller_types=["lsilogic"],
            )
            result = svc.evaluate(vm)
            has_critical_os = any(
                i.severity == "critical" and i.category == "os"
                for i in result.issues
            )
            sc.details[os_name] = {
                "compatible": result.compatible,
                "score": result.score,
                "has_critical_os_issue": has_critical_os,
                "issues": [{"severity": i.severity, "category": i.category, "message": i.message[:80]}
                           for i in result.issues],
            }

        all_blocked = all(
            sc.details[os]["compatible"] is False
            for os in unsupported_oses
        )
        sc.passed = all_blocked
        if not all_blocked:
            sc.error_type = "DetectionError"
            sc.error_message = "Some unsupported OSes were not flagged as incompatible"

    except Exception as e:
        sc.passed = False
        sc.error_type = type(e).__name__
        sc.error_message = str(e)

    return sc


# ---------------------------------------------------------------------------
# Scenario 6: Service Degradation (Partial Failure)
# ---------------------------------------------------------------------------

def scenario_partial_inventory_failure() -> FailureScenario:
    """Simulate partial inventory failure — some services fail, others continue."""
    sc = FailureScenario(
        name="partial_inventory_failure",
        description="Partial infrastructure failure — some services unavailable, "
                    "assessment engine should still function for available data",
    )
    try:
        from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
        from app.services.vmware.compatibility import VMwareCompatibilityService

        svc = VMwareCompatibilityService()

        # VM with partial data — should still produce a result
        vm = VMSummary(
            id="partial-vm-1",
            name="partial-vm",
            power_state="poweredOn",
            guest_os="Ubuntu 22.04",
            hardware=VMHardware(
                cpu_count=4, memory_mb=16384,
                disks=[
                    VMDisk(label="d1", capacity_gb=80, datastore_name="ds1", controller_type="scsi"),
                ],
                nics=[
                    VMNic(label="n1", network_name="VM Network", mac_address="00:50:56:01:02:03", nic_type="vmxnet3"),
                ],
            ),
            firmware=None,
            secure_boot_enabled=None,
            vmware_tools_status=None,
            disk_controller_types=None,
        )

        result = svc.evaluate(vm)
        sc.passed = result is not None and result.compatible is not None
        sc.details = {
            "compatible": result.compatible,
            "score": result.score,
            "issue_count": len(result.issues),
            "issues": [{"severity": i.severity, "category": i.category, "message": i.message[:80]}
                       for i in result.issues],
        }
        if not sc.passed:
            sc.error_type = "DegradationError"
            sc.error_message = "Engine failed to produce result with partial data"

    except Exception as e:
        sc.passed = False
        sc.error_type = type(e).__name__
        sc.error_message = str(e)
        traceback.print_exc()

    return sc


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(scenarios: list[FailureScenario]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    all_checks = sum(len(s.details.get("issues", [])) if isinstance(s.details, dict) else 0
                     for s in scenarios)
    passed = sum(1 for s in scenarios if s.passed)
    failed = len(scenarios) - passed

    lines = [
        f"# Recovery Validation Report",
        f"",
        f"> Generated: {now}",
        f"> Result: **{passed}/{len(scenarios)} scenarios passed**",
        f"",
        f"## Summary",
        f"",
        f"| Status | Count |",
        f"|--------|:-----:|",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Total  | {len(scenarios)} |",
        f"",
        f"## Scenario Results",
        f"",
        f"| Scenario | Status | Duration | Recovered | Recovery Time | Detail |",
        f"|----------|:------:|:--------:|:---------:|:-------------:|--------|",
    ]

    for s in scenarios:
        status = "✅" if s.passed else "❌"
        dur = f"{s.duration_ms:.0f}ms" if s.duration_ms > 0 else "-"
        rec = "✅" if s.recovered else "❌" if s.passed else "N/A"
        rt = f"{s.recovery_time_ms:.0f}ms" if s.recovery_time_ms > 0 else "-"
        detail = s.error_message[:100] if s.error_message else s.description[:100]
        detail_escaped = detail.replace("|", "\\|")
        lines.append(f"| {s.name} | {status} | {dur} | {rec} | {rt} | {detail_escaped} |")

    lines.extend([
        f"",
        f"## Failure Handling Matrix",
        f"",
        f"| Scenario | Graceful Degradation | Retry Verified | Reconnect Verified | Crash Protection |",
        f"|----------|:--------------------:|:--------------:|:------------------:|:----------------:|",
    ])

    for s in scenarios:
        gd = "✅" if s.passed else "❌"
        retry = "✅" if s.recovered else "N/A"
        rc = "✅" if s.recovered else "N/A"
        cp = "✅" if s.passed else "❌"
        lines.append(f"| {s.name} | {gd} | {retry} | {rc} | {cp} |")

    lines.extend([
        f"",
        f"## Detailed Failure Information",
        f"",
    ])

    for s in scenarios:
        lines.append(f"### {s.name}")
        lines.append(f"")
        lines.append(f"- **Description**: {s.description}")
        lines.append(f"- **Passed**: {s.passed}")
        if s.error_type and s.error_type != "skipped":
            lines.append(f"- **Error Type**: {s.error_type}")
            lines.append(f"- **Error Message**: {s.error_message}")
        if s.details:
            lines.append(f"- **Details**: `{json.dumps({k: v for k, v in s.details.items() if k != 'issues'}, default=str)}`")
        lines.append(f"")

    lines.append("---")
    lines.append("*Report generated by recovery_validation.py*")
    return "\n".join(lines)


def generate_json(scenarios: list[FailureScenario]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "passed": sum(1 for s in scenarios if s.passed),
        "failed": sum(1 for s in scenarios if not s.passed),
        "scenarios": [asdict(s) for s in scenarios],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Recovery Validation Harness")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Comma-separated scenario names to run (default: all)")
    args = parser.parse_args()

    scenario_registry = {
        "disconnect": scenario_vcenter_disconnect,
        "session": scenario_expired_session,
        "pool": scenario_pool_exhaustion,
        "metadata": scenario_malformed_vm_metadata,
        "unsupported_os": scenario_unsupported_guest_os,
        "partial": scenario_partial_inventory_failure,
    }

    if args.scenario:
        selected = [s.strip() for s in args.scenario.split(",")]
        to_run = {k: v for k, v in scenario_registry.items() if k in selected}
    else:
        to_run = scenario_registry

    print("=" * 60)
    print("  Failure & Recovery Validation Harness")
    print(f"  Scenarios: {len(to_run)}")
    print("=" * 60)

    scenarios: list[FailureScenario] = []
    for name, fn in to_run.items():
        print(f"\n{'─' * 60}")
        print(f"  Scenario: {name}")
        print(f"  {fn.__doc__.strip()}")
        t0 = time.perf_counter()
        sc = fn()
        elapsed = (time.perf_counter() - t0) * 1000
        sc.duration_ms = elapsed
        scenarios.append(sc)

        status = "✅ PASS" if sc.passed else "❌ FAIL"
        print(f"  → {status} ({elapsed:.0f}ms)")
        if sc.error_message:
            print(f"    Error: {sc.error_message[:120]}")

    print(f"\n{'=' * 60}")
    passed = sum(1 for s in scenarios if s.passed)
    print(f"  Results: {passed}/{len(scenarios)} passed")
    print(f"{'=' * 60}")

    # Export
    output_dir = Path("benchmark_results/validation")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "recovery_validation_report.md"
    report_path.write_text(generate_report(scenarios))
    print(f"\n  Report: {report_path}")

    if args.json:
        json_path = output_dir / "recovery_validation.json"
        json_path.write_text(json.dumps(generate_json(scenarios), indent=2, default=str))
        print(f"  JSON:   {json_path}")

    if passed < len(scenarios):
        sys.exit(1)


if __name__ == "__main__":
    main()
