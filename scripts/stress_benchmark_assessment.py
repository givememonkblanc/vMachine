#!/usr/bin/env python3
"""Large-Scale Stress Benchmark — Phase 5.

Extends the synthetic benchmark to 1000 VMs and adds stress-specific
measurements: connection pool behavior, memory stability, timeout handling,
and parallel assessment scaling analysis.

Usage
-----
    PYTHONPATH=. python scripts/stress_benchmark_assessment.py
    PYTHONPATH=. python scripts/stress_benchmark_assessment.py --json
    PYTHONPATH=. python scripts/stress_benchmark_assessment.py --quick
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ["APP_ENV"] = "benchmark"

# ---------------------------------------------------------------------------
# Attempt optional dependencies
# ---------------------------------------------------------------------------
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Project imports
from app.schemas.vmware.assessment import (
    CompatibilityIssueDetail,
    FlavorMatchResult,
    NetworkMappingResult,
    DiskMappingResult,
    ScoredCompatibilityResult,
    VMMappingResult,
)
from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
from app.services.vmware.compatibility import VMwareCompatibilityService
from app.services.vmware.plan_service import VMwarePlanService


STRESS_SIZES = [100, 500, 1000]
WARM_CACHE_ITERATIONS = 3

MOCK_FLAVORS: list[tuple[str, int, int, int]] = [
    ("m1.tiny", 1, 512, 1),
    ("m1.small", 1, 2048, 20),
    ("m1.medium", 2, 4096, 40),
    ("m1.large", 4, 8192, 80),
    ("m1.xlarge", 8, 16384, 160),
    ("m1.2xlarge", 12, 32768, 320),
    ("m1.4xlarge", 16, 65536, 640),
    ("m1.8xlarge", 32, 131072, 1280),
    ("m1.16xlarge", 48, 262144, 2560),
    ("m1.32xlarge", 64, 524288, 5120),
]

MOCK_OS_TEMPLATES: list[str] = [
    "CentOS 7", "CentOS 8", "CentOS 9",
    "Ubuntu 20.04", "Ubuntu 22.04", "Ubuntu 24.04",
    "Debian 11", "Debian 12",
    "Red Hat Enterprise Linux 8", "Red Hat Enterprise Linux 9",
    "SUSE Linux Enterprise Server 15",
    "Windows Server 2019", "Windows Server 2022",
    "Windows 10", "Windows 11",
    "FreeBSD 13", "FreeBSD 14",
    "Solaris 11",  # unsupported
    "macOS Ventura",  # unsupported
    "HP-UX 11i",  # unsupported
]

MOCK_POWER_STATES: list[str] = [
    "poweredOn", "poweredOff", "suspended",
] * 3  # bias toward poweredOn

MOCK_TOOLS_STATUSES: list[str] = [
    "toolsOk", "toolsOk", "toolsOk",  # bias toward OK
    "toolsNotRunning",
    "toolsNotInstalled",
    None,
]

MOCK_DISK_CONTROLLER_SETS: list[list[str]] = [
    ["lsilogic"],
    ["lsilogic", "ide"],
    ["pvscsi"],
    ["nvme"],
    ["lsilogic", "nvme"],
    ["sata"],
    ["ide"],
    [],
]

MOCK_NIC_TYPES: list[str] = [
    "vmxnet3", "vmxnet3", "vmxnet3",  # bias toward modern
    "e1000", "vmxnet2", "sriov", "unknown",
]


def _get_rss_mb() -> float:
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    return 0.0


def _generate_mock_vms(count: int) -> list[VMSummary]:
    vms: list[VMSummary] = []
    for i in range(count):
        os_name = MOCK_OS_TEMPLATES[i % len(MOCK_OS_TEMPLATES)]
        power = MOCK_POWER_STATES[i % len(MOCK_POWER_STATES)]
        tools = MOCK_TOOLS_STATUSES[i % len(MOCK_TOOLS_STATUSES)]

        # Vary hardware config to produce diverse compatibility results
        cpu_count = (i % 16) + 1
        memory_mb = ((i % 8) + 1) * 1024
        disk_count = (i % 4) + 1
        nic_count = (i % 3) + 1

        # Occasionally produce edge cases
        if i % 13 == 0:
            cpu_count = 0  # no vCPUs
        if i % 17 == 0:
            memory_mb = 0  # no memory
        if i % 19 == 0:
            disk_count = 0  # no disks
        if i % 23 == 0:
            os_name = "Unknown OS " + str(i)

        controllers = MOCK_DISK_CONTROLLER_SETS[i % len(MOCK_DISK_CONTROLLER_SETS)]

        firmware = "bios"
        secure_boot = False
        if i % 7 == 0:
            firmware = "efi"
        if i % 11 == 0:
            firmware = "efi"
            secure_boot = True

        disks = [
            VMDisk(
                label=f"disk{j}",
                capacity_gb=((i * j + 10) % 500) + 10,
                datastore=f"datastore{j % 3 + 1}",
                controller_type=controllers[j % len(controllers)] if controllers else "scsi",
            )
            for j in range(disk_count)
        ]

        nics = [
            VMNic(
                label=f"nic{j}",
                mac_address=f"00:50:56:{(i % 256):02x}:{j:02x}:{(i * j % 256):02x}",
                network_name=f"VM Network {j % 5 + 1}",
                nic_type=MOCK_NIC_TYPES[(i + j) % len(MOCK_NIC_TYPES)],
            )
            for j in range(nic_count)
        ]

        hw = VMHardware(
            cpu_count=cpu_count,
            memory_mb=memory_mb,
            disks=disks,
            nics=nics,
        )

        vms.append(
            VMSummary(
                id=f"vm-{i:04d}",
                name=f"stress-vm-{i:04d}-{os_name[:10].replace(' ', '-')}",
                power_state=power,
                guest_os=os_name,
                hardware=hw,
                firmware=firmware,
                secure_boot_enabled=secure_boot,
                vmware_tools_status=tools,
                disk_controller_types=list(set(controllers)) if controllers else [],
            )
        )
    return vms


# ---------------------------------------------------------------------------
# Benchmark data structures
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkSample:
    name: str
    values_ms: list[float] = field(default_factory=list)

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.values_ms) if self.values_ms else 0.0

    @property
    def p50_ms(self) -> float:
        s = sorted(self.values_ms)
        return s[len(s) // 2] if s else 0.0

    @property
    def p95_ms(self) -> float:
        s = sorted(self.values_ms)
        return s[int(len(s) * 0.95)] if s else 0.0

    @property
    def p99_ms(self) -> float:
        s = sorted(self.values_ms)
        return s[int(len(s) * 0.99)] if s else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.values_ms) if self.values_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.values_ms) if self.values_ms else 0.0

    def throughput(self, vm_count: int) -> float:
        if not self.values_ms:
            return 0.0
        return (vm_count / (self.avg_ms / 1000)) if self.avg_ms > 0 else 0.0


@dataclass
class StressRun:
    vm_count: int
    results: dict[str, BenchmarkSample] = field(default_factory=dict)
    mem_before_mb: float = 0.0
    mem_after_mb: float = 0.0
    mem_delta_mb: float = 0.0
    timeout_count: int = 0
    error_count: int = 0


# ---------------------------------------------------------------------------
# Benchmark functions
# ---------------------------------------------------------------------------

def benchmark_compatibility(vms: list[VMSummary], repeat: int = 1) -> BenchmarkSample:
    svc = VMwareCompatibilityService()
    sample = BenchmarkSample(name="Compatibility Check")
    for _ in range(repeat):
        start = time.perf_counter()
        for vm in vms:
            svc.evaluate(vm)
        elapsed = (time.perf_counter() - start) * 1000
        sample.values_ms.append(elapsed)
    return sample


def benchmark_plan_generation(vms: list[VMSummary], repeat: int = 1) -> BenchmarkSample:
    svc = VMwareCompatibilityService()
    plan_svc = VMwarePlanService()
    sample = BenchmarkSample(name="Plan Generation")
    for _ in range(repeat):
        results_list = [(vm, svc.evaluate(vm), None) for vm in vms]
        start = time.perf_counter()
        plan_svc.generate_plan(results_list)
        elapsed = (time.perf_counter() - start) * 1000
        sample.values_ms.append(elapsed)
    return sample


async def benchmark_parallel_assessment(
    vms: list[VMSummary], max_concurrency: int = 10, repeat: int = 3
) -> BenchmarkSample:
    sample = BenchmarkSample(name=f"Parallel (concurrency={max_concurrency})")
    svc = VMwareCompatibilityService()

    async def _eval_one(vm: VMSummary) -> Any:
        svc.evaluate(vm)
        return True

    import asyncio

    for _ in range(repeat):
        sem = asyncio.Semaphore(max_concurrency)

        async def _limited(vm: VMSummary) -> Any:
            async with sem:
                return await _eval_one(vm)

        start = time.perf_counter()
        await asyncio.gather(*[_limited(vm) for vm in vms])
        elapsed = (time.perf_counter() - start) * 1000
        sample.values_ms.append(elapsed)
    return sample


# ---------------------------------------------------------------------------
# Stress-specific measurements
# ---------------------------------------------------------------------------

def measure_memory_stability(vms: list[VMSummary], repeat: int = 5) -> dict[str, Any]:
    """Measure memory growth across repeated evaluation cycles."""
    svc = VMwareCompatibilityService()
    mem_readings: list[float] = []
    for i in range(repeat):
        for vm in vms:
            svc.evaluate(vm)
        mem_readings.append(_get_rss_mb())
    return {
        "readings": [round(m, 1) for m in mem_readings],
        "min_mb": round(min(mem_readings), 1),
        "max_mb": round(max(mem_readings), 1),
        "delta_mb": round(max(mem_readings) - min(mem_readings), 1),
        "leak_detected": (max(mem_readings) - min(mem_readings)) > 10,
    }


def measure_timeout_behavior(vms: list[VMSummary], timeout_s: float = 0.001) -> dict[str, Any]:
    """Simulate per-VM timeout and count how many VMs exceed it."""
    svc = VMwareCompatibilityService()
    timed_out = 0
    completed = 0
    for vm in vms:
        start = time.perf_counter()
        svc.evaluate(vm)
        elapsed = time.perf_counter() - start
        if elapsed > timeout_s:
            timed_out += 1
        completed += 1
    return {
        "timeout_threshold_s": timeout_s,
        "timed_out": timed_out,
        "completed": completed,
        "timeout_pct": round(timed_out / completed * 100, 2) if completed else 0,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _generate_report(all_runs: list[StressRun], memory_stability: dict[str, Any],
                     timeout_results: dict[str, Any]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# Stress Validation Report",
        f"",
        f"> Generated: {now}",
        f"> Environment: {os.uname().sysname} {os.uname().release}",
        f"> Memory: {_get_rss_mb():.0f} MB total (current process)",
        f"",
        f"## Summary",
        f"",
        f"| VM Count | Compatibility | Plan Generation | Parallel (concurrency=10) | Mem Delta |",
        f"|:--------:|:-------------:|:---------------:|:-------------------------:|:---------:|",
    ]

    for run in all_runs:
        compat = run.results.get("Compatibility Check")
        plan = run.results.get("Plan Generation")
        parallel = run.results.get("Parallel (concurrency=10)")
        cd = f"{compat.avg_ms:.2f} ms" if compat else "-"
        pd = f"{plan.avg_ms:.2f} ms" if plan else "-"
        pard = f"{parallel.avg_ms:.2f} ms" if parallel else "-"
        lines.append(
            f"| {run.vm_count} | {cd} | {pd} | {pard} | "
            f"{run.mem_delta_mb:+.1f} MB |"
        )

    lines.extend([
        f"",
        f"## Latency Details",
        f"",
        f"| VM Count | Operation | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (VM/s) |",
        f"|:--------:|-----------|:--------:|:--------:|:--------:|:--------:|:-----------------:|",
    ])

    for run in all_runs:
        for name, sample in run.results.items():
            lines.append(
                f"| {run.vm_count} | {name} | {sample.avg_ms:.2f} | "
                f"{sample.p50_ms:.2f} | {sample.p95_ms:.2f} | "
                f"{sample.p99_ms:.2f} | "
                f"{sample.throughput(run.vm_count):.0f} |"
            )

    lines.extend([
        f"",
        f"## Memory Stability",
        f"",
        f"| Metric | Value |",
        f"|--------|:-----:|",
        f"| Min RSS | {memory_stability['min_mb']} MB |",
        f"| Max RSS | {memory_stability['max_mb']} MB |",
        f"| Delta | {memory_stability['delta_mb']} MB |",
        f"| Readings | {memory_stability['readings']} |",
        f"| Leak suspected | {'⚠️ YES' if memory_stability['leak_detected'] else '✅ No'} |",
        f"",
        f"## Timeout Analysis",
        f"",
        f"| Metric | Value |",
        f"|--------|:-----:|",
        f"| Threshold | {timeout_results['timeout_threshold_s']}s |",
        f"| VMs exceeding threshold | {timeout_results['timed_out']}/{timeout_results['completed']} "
        f"({timeout_results['timeout_pct']}%) |",
        f"",
        f"## Pool Behavior Notes",
        f"",
        f"- Connection pool: synthetic mock (no real vCenter)",
        f"- Pool reuse: N/A (synthetic)",
        f"- Reconnect count: N/A (synthetic)",
        f"- For live pool testing, run `scripts/validate_vcenter.py` against real vCenter",
        f"",
        f"---",
        f"",
        f"## Known Limitations",
        f"",
        f"1. Synthetic stress uses generated VMSummary objects — no pyVmomi serialization overhead",
        f"2. Connection pool behavior not tested (no real vCenter)",
        f"3. Redis cache efficiency not tested (in-memory cache only)",
        f"4. DB persistence under load not tested (in-process evaluation only)",
        f"5. Real-world timeout behavior depends on vCenter/OpenStack API latency",
        f"",
        f"---",
        f"*Report generated by stress_benchmark_assessment.py*",
    ])
    return "\n".join(lines)


def _generate_json(all_runs: list[StressRun], memory_stability: dict[str, Any],
                   timeout_results: dict[str, Any]) -> dict:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "runs": [
            {
                "vm_count": r.vm_count,
                "mem_before_mb": r.mem_before_mb,
                "mem_after_mb": r.mem_after_mb,
                "mem_delta_mb": r.mem_delta_mb,
                "timeout_count": r.timeout_count,
                "error_count": r.error_count,
                "results": {
                    name: {
                        "avg_ms": s.avg_ms,
                        "p50_ms": s.p50_ms,
                        "p95_ms": s.p95_ms,
                        "p99_ms": s.p99_ms,
                        "min_ms": s.min_ms,
                        "max_ms": s.max_ms,
                        "throughput_vm_per_s": s.throughput(r.vm_count),
                    }
                    for name, s in r.results.items()
                },
            }
            for r in all_runs
        ],
        "memory_stability": memory_stability,
        "timeout_analysis": timeout_results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Stress Benchmark for Assessment Engine")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    parser.add_argument("--quick", action="store_true", help="Run 100 and 1000 only")
    args = parser.parse_args()

    sizes = [100, 1000] if args.quick else STRESS_SIZES

    print("=" * 72)
    print("  VMware Assessment Engine — Stress Benchmark")
    print(f"  CPU: {os.uname().machine}")
    print(f"  Memory: {_get_rss_mb():.1f} MB (current)")
    print(f"  VM sizes: {sizes}")
    print("=" * 72)

    all_runs: list[StressRun] = []
    first_run = True

    for vm_count in sizes:
        print(f"\n{'─' * 72}")
        print(f"  Generating {vm_count} mock VMs...")
        vms = _generate_mock_vms(vm_count)
        print(f"  Done. {len(vms)} VMs created.")

        run = StressRun(vm_count=vm_count)
        run.mem_before_mb = _get_rss_mb()

        # Compatibility
        print(f"  Benchmarking compatibility ({vm_count} VMs)...")
        sample = benchmark_compatibility(vms, repeat=WARM_CACHE_ITERATIONS)
        run.results[sample.name] = sample
        print(f"    Avg: {sample.avg_ms:.2f} ms  Throughput: {sample.throughput(vm_count):.0f} VM/s")

        # Plan generation
        print(f"  Benchmarking plan generation ({vm_count} VMs)...")
        sample = benchmark_plan_generation(vms, repeat=WARM_CACHE_ITERATIONS)
        run.results[sample.name] = sample
        print(f"    Avg: {sample.avg_ms:.2f} ms")

        # Parallel assessment
        print(f"  Benchmarking parallel assessment ({vm_count} VMs, concurrency=10)...")
        sample = await benchmark_parallel_assessment(vms, max_concurrency=10, repeat=3)
        run.results[sample.name] = sample
        print(f"    Avg: {sample.avg_ms:.2f} ms  Throughput: {sample.throughput(vm_count):.0f} VM/s")

        run.mem_after_mb = _get_rss_mb()
        run.mem_delta_mb = run.mem_after_mb - run.mem_before_mb
        all_runs.append(run)

        # Memory stability test — run only once on the largest batch
        if first_run:
            first_run = False
            print(f"\n  Measuring memory stability ({vm_count} VMs, 5 cycles)...")
            mem_stability = measure_memory_stability(vms, repeat=5)
            print(f"    Min: {mem_stability['min_mb']:.1f} MB  Max: {mem_stability['max_mb']:.1f} MB  "
                  f"Delta: {mem_stability['delta_mb']:.1f} MB")
            if mem_stability['leak_detected']:
                print(f"    ⚠️  Possible memory leak detected (delta > 10 MB)")

    # Timeout analysis — run on all VMs combined
    print(f"\n  Analyzing timeout behavior...")
    combined_vms = _generate_mock_vms(sum(sizes))
    timeout_results = measure_timeout_behavior(combined_vms, timeout_s=0.001)
    print(f"    VMs exceeding 1ms threshold: {timeout_results['timed_out']}/{timeout_results['completed']} "
          f"({timeout_results['timeout_pct']}%)")

    # Generate report
    report = _generate_report(all_runs, mem_stability, timeout_results)

    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "stress_validation_report.md"
    report_path.write_text(report)
    print(f"\n{'─' * 72}")
    print(f"  Report written to {report_path}")

    if args.json:
        json_dir = Path("benchmark_results") / "stress"
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / "stress_assessment.json"
        json_path.write_text(
            json.dumps(_generate_json(all_runs, mem_stability, timeout_results), indent=2, default=str)
        )
        print(f"  JSON written to {json_path}")

    print(f"\n{'=' * 72}")
    print("  Stress benchmark complete.")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
