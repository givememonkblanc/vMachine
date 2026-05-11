#!/usr/bin/env python3
"""VMware Migration Assessment — synthetic benchmark suite.

Simulates 10 / 50 / 100 / 500 VMs with realistic VMSummary payloads and
measures the latency of every Phase-4 service *without* requiring a live
vCenter or OpenStack.

Usage
-----
    python scripts/benchmark_vmware_assessment.py [--json]

Optional flags
--------------
    --json          Export per-run results to benchmark_results/vmware_assessment.json
    --quick         Run only 10/100 VM sizes (skips 50/500 for faster iteration)
    --warm-only     Skip cold-cache measurements
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Attempt optional dependencies
# ---------------------------------------------------------------------------
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Project imports  —  all pure-logic services can be imported without a DB
# ---------------------------------------------------------------------------
os.environ["APP_ENV"] = "benchmark"  # prevent side-effects

from app.schemas.vmware.assessment import (
    ScoredCompatibilityResult,
    VMMappingResult,
)
from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
from app.services.vmware.compatibility import VMwareCompatibilityService
from app.services.vmware.plan_service import VMwarePlanService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VM_SIZES = [10, 50, 100, 500]
WARM_CACHE_ITERATIONS = 3  # how many sequential batches to run for "warm"

# 20 realistic OpenStack flavors for mapping benchmark
MOCK_FLAVORS: list[tuple[str, int, int, int]] = [
    ("m1.tiny", 1, 512, 1),
    ("m1.small", 1, 2048, 20),
    ("m1.medium", 2, 4096, 40),
    ("m1.large", 4, 8192, 80),
    ("m1.xlarge", 8, 16384, 160),
    ("m1.2xlarge", 12, 32768, 320),
    ("m1.4xlarge", 16, 65536, 640),
    ("m1.8xlarge", 32, 131072, 1280),
    ("gpu.medium", 8, 32768, 100),
    ("gpu.large", 16, 65536, 200),
    ("compute.optimized", 32, 65536, 100),
    ("memory.optimized", 16, 131072, 200),
    ("storage.optimized", 8, 32768, 2000),
    ("windows.medium", 4, 8192, 80),
    ("windows.large", 8, 16384, 200),
    ("custom.cpu-heavy", 48, 131072, 400),
    ("custom.mem-heavy", 32, 262144, 200),
    ("custom.huge", 64, 524288, 4000),
    ("tiny.nested", 1, 256, 1),
    ("ephemeral.small", 2, 4096, 0),
]

MOCK_NETWORKS: list[tuple[str, str]] = [
    ("internal-mgmt", "net-internal-mgmt"),
    ("external-public", "net-external-public"),
    ("storage-backend", "net-storage-backend"),
    ("dmz", "net-dmz"),
    ("dev-vlan-100", "net-dev-vlan-100"),
    ("prod-vlan-200", "net-prod-vlan-200"),
    ("db-tier", "net-db-tier"),
]

VMDisk.__hash__ = lambda self: hash(id(self))


# ===================================================================
#  Mock VM generator
# ===================================================================

OS_TEMPLATES: list[dict[str, Any]] = [
    {"guest_os": "CentOS 7.9.2009", "firmware": "bios"},
    {"guest_os": "Ubuntu 22.04.3 LTS", "firmware": "bios"},
    {"guest_os": "Red Hat Enterprise Linux 8.8", "firmware": "bios"},
    {"guest_os": "Windows Server 2022 Datacenter", "firmware": "efi"},
    {"guest_os": "Windows Server 2019 Standard", "firmware": "efi"},
    {"guest_os": "Debian GNU/Linux 12 (bookworm)", "firmware": "bios"},
    {"guest_os": "SUSE Linux Enterprise Server 15 SP5", "firmware": "bios"},
    {"guest_os": "Oracle Linux Server 8.8", "firmware": "bios"},
    {"guest_os": "Rocky Linux 9.2", "firmware": "bios"},
    {"guest_os": "FreeBSD 13.2-RELEASE", "firmware": "bios"},
    {"guest_os": "Windows 11 Pro", "firmware": "efi"},
    {"guest_os": "Windows 10 Enterprise", "firmware": "bios"},
    {"guest_os": "AlmaLinux 9.2", "firmware": "bios"},
    {"guest_os": "Fedora 38", "firmware": "bios"},
    {"guest_os": "Solaris 11.4", "firmware": "bios"},
    {"guest_os": "Ubuntu 20.04.6 LTS", "firmware": "efi", "secure_boot": True},
    {
        "guest_os": "Windows Server 2016 Standard",
        "firmware": "efi",
        "secure_boot": True,
    },
    {"guest_os": "CentOS Stream 9", "firmware": "efi"},
    {"guest_os": "macOS 14 Sonoma", "firmware": "efi"},
    {"guest_os": None, "firmware": "bios"},
]

POWER_STATES = ("poweredOn", "poweredOff", "suspended")
TOOLS_STATUSES = ("toolsOk", "toolsNotInstalled", "toolsNotRunning", "toolsOld", None)
DISK_CONTROLLER_SETS = [
    ["pvscsi"],
    ["lsilogic"],
    ["nvme"],
    ["pvscsi", "sata"],
    ["lsilogic", "ide"],
    ["nvme", "pvscsi"],
    ["ide"],
    None,
]
NIC_TYPES = ("vmxnet3", "e1000", "vmxnet2", "e1000e", "sriov")


def _generate_mock_vms(count: int) -> list[VMSummary]:
    vms: list[VMSummary] = []
    for i in range(count):
        tmpl = OS_TEMPLATES[i % len(OS_TEMPLATES)]
        power = POWER_STATES[i % len(POWER_STATES)]
        controller_set = DISK_CONTROLLER_SETS[i % len(DISK_CONTROLLER_SETS)]

        # Realistic hardware: vary across VM counts
        cpu = (i % 16) + 1
        if cpu == 1 and i % 7 == 0:
            cpu = 0  # occasionally broken
        mem = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536][i % 8]
        if mem == 512 and i % 11 == 0:
            mem = 0  # occasionally broken

        n_disks = (i % 5) + 1
        disks = [
            VMDisk(
                label=f"Hard disk {d + 1}",
                capacity_gb=[20, 40, 80, 100, 200, 500, 1000, 2000][(i + d) % 8],
                thin_provisioned=(i + d) % 3 != 0,
                datastore_name=f"datastore-{(i + d) % 4 + 1}",
                controller_type=controller_set[d % len(controller_set)]
                if controller_set
                else None,
            )
            for d in range(n_disks)
        ]

        n_nics = (i % 3) + 1
        nic_type = NIC_TYPES[i % len(NIC_TYPES)]
        nics = [
            VMNic(
                label=f"Network adapter {n + 1}",
                network_name=MOCK_NETWORKS[(i + n) % len(MOCK_NETWORKS)][0],
                mac_address=f"00:50:56:{i:02x}:{n:02x}:{(i + n) % 256:02x}",
                ip_addresses=[f"10.0.{i}.{n + 1}"],
                nic_type=nic_type,
            )
            for n in range(n_nics)
        ]

        tools = TOOLS_STATUSES[i % len(TOOLS_STATUSES)]

        vm = VMSummary(
            id=f"vm-{i:04d}",
            name=f"bench-vm-{i:04d}",
            power_state=power,
            guest_os=tmpl["guest_os"],
            hardware=VMHardware(
                cpu_count=cpu,
                cpu_cores_per_socket=min(cpu, 4) if cpu > 0 else 1,
                memory_mb=mem,
                disks=disks,
                nics=nics,
            ),
            cluster_name=f"cluster-{i % 5 + 1}",
            datastores=list({d.datastore_name for d in disks if d.datastore_name}),
            tags=[f"env-{['dev', 'staging', 'prod'][i % 3]}"] if i % 2 == 0 else [],
            annotation=f"Benchmark VM #{i} — {tmpl['guest_os'] or 'Unknown OS'}",
            firmware=tmpl["firmware"],
            secure_boot_enabled=tmpl.get("secure_boot", False),
            vmware_tools_status=tools,
            disk_controller_types=controller_set,
        )
        vms.append(vm)
    return vms


# ===================================================================
#  Mock OpenStack factory for the mapping engine
# ===================================================================


class _MockOSObj:
    """Mimics the SDK objects returned by OpenStackConnectionFactory.call()."""

    def __init__(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


class MockOpenStackFactory:
    """In-process fake that returns pre-defined flavors & networks."""

    def call(self, service: str, resource: str) -> list[Any]:
        if service == "compute" and resource == "flavors":
            return [
                _MockOSObj(id=f"flavor-{i}", name=name, vcpus=vcpu, ram=ram, disk=disk)
                for i, (name, vcpu, ram, disk) in enumerate(MOCK_FLAVORS)
            ]
        if service == "network" and resource == "networks":
            return [_MockOSObj(id=nid, name=name) for name, nid in MOCK_NETWORKS]
        return []
        return []


# ===================================================================
#  Measurement helpers
# ===================================================================


@dataclass
class LatencySample:
    name: str
    values_ms: list[float] = field(default_factory=list)

    def record(self, duration_s: float) -> None:
        self.values_ms.append(round(duration_s * 1000, 4))

    @property
    def count(self) -> int:
        return len(self.values_ms)

    @property
    def avg_ms(self) -> float:
        return round(statistics.mean(self.values_ms), 2) if self.values_ms else 0.0

    @property
    def p50_ms(self) -> float:
        return round(statistics.median(self.values_ms), 2) if self.values_ms else 0.0

    @property
    def p95_ms(self) -> float:
        if len(self.values_ms) < 2:
            return self.avg_ms
        s = sorted(self.values_ms)
        return round(s[int(len(s) * 0.95)], 2)

    @property
    def p99_ms(self) -> float:
        if len(self.values_ms) < 2:
            return self.avg_ms
        s = sorted(self.values_ms)
        return round(s[int(len(s) * 0.99)], 2)

    @property
    def min_ms(self) -> float:
        return round(min(self.values_ms), 2) if self.values_ms else 0.0

    @property
    def max_ms(self) -> float:
        return round(max(self.values_ms), 2) if self.values_ms else 0.0

    def throughput(self, batch_size: int) -> float:
        if not self.values_ms:
            return 0.0
        total_s = sum(self.values_ms) / 1000
        return round(batch_size / total_s, 1) if total_s > 0 else 0.0

    def report_row(self, batch_size: int, label: str = "") -> str:
        tput = self.throughput(batch_size)
        extras = f" | {tput:>8.1f} VM/s" if label else ""
        return (
            f"| {label or self.name:<45s} | {self.avg_ms:>8.2f} |"
            f" {self.p50_ms:>8.2f} | {self.p95_ms:>8.2f} |"
            f" {self.p99_ms:>8.2f} | {self.min_ms:>8.2f} | {self.max_ms:>8.2f}{extras} |"
        )


@dataclass
class BenchmarkRun:
    vm_count: int
    results: dict[str, LatencySample] = field(default_factory=dict)
    mem_before_mb: float = 0.0
    mem_after_mb: float = 0.0

    def add(self, name: str, values: list[float]) -> LatencySample:
        sample = LatencySample(name=name, values_ms=values)
        self.results[name] = sample
        return sample


def _get_rss_mb() -> float:
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    return 0.0


async def _measure_async(coro: Any, timeout_s: float = 60) -> float:
    """Execute coroutine and return wall-clock seconds."""
    start = time.perf_counter()
    await asyncio.wait_for(coro, timeout=timeout_s)
    return time.perf_counter() - start


async def _measure_async_batch(
    label: str,
    coro_factory: Any,
    repeat: int,
    sample: LatencySample,
) -> None:
    for _ in range(repeat):
        dur = await _measure_async(coro_factory())
        sample.record(dur)


# ===================================================================
#  Individual benchmarks
# ===================================================================


def benchmark_compatibility(vms: list[VMSummary], repeat: int = 5) -> LatencySample:
    svc = VMwareCompatibilityService()
    sample = LatencySample("Compatibility Check")
    for _ in range(repeat):
        start = time.perf_counter()
        for vm in vms:
            svc.evaluate(vm)
        sample.record(time.perf_counter() - start)
    return sample


def benchmark_mapping(vms: list[VMSummary], repeat: int = 5) -> LatencySample:
    factory = MockOpenStackFactory()
    from app.services.vmware.mapping_engine import VMwareMappingEngine

    engine = VMwareMappingEngine(factory)
    engine._flavor_cache = None  # force cache-miss on first call
    engine._network_cache = None

    sample = LatencySample("Resource Mapping")
    for _ in range(repeat):
        start = time.perf_counter()
        for vm in vms:
            engine.map_vm(vm)
        sample.record(time.perf_counter() - start)
    return sample


def benchmark_mapping_warm(vms: list[VMSummary], repeat: int = 5) -> LatencySample:
    factory = MockOpenStackFactory()
    from app.services.vmware.mapping_engine import VMwareMappingEngine

    engine = VMwareMappingEngine(factory)
    engine._flavor_cache = None
    engine._network_cache = None
    engine.map_vm(vms[0]) if vms else None  # seed caches

    sample = LatencySample("Resource Mapping (warm cache)")
    for _ in range(repeat):
        start = time.perf_counter()
        for vm in vms:
            engine.map_vm(vm)
        sample.record(time.perf_counter() - start)
    return sample


def benchmark_plan_generation(vms: list[VMSummary], repeat: int = 5) -> LatencySample:
    factory = MockOpenStackFactory()
    from app.services.vmware.mapping_engine import VMwareMappingEngine

    compat_svc = VMwareCompatibilityService()
    engine = VMwareMappingEngine(factory)
    plan_svc = VMwarePlanService()

    # Pre-compute compatibility + mapping once
    compat_results: list[ScoredCompatibilityResult] = []
    mapping_results: list[VMMappingResult] = []
    for vm in vms:
        compat_results.append(compat_svc.evaluate(vm))
        mapping_results.append(engine.map_vm(vm))

    sample = LatencySample("Plan Generation")
    for _ in range(repeat):
        tuples = list(zip(vms, compat_results, mapping_results))
        start = time.perf_counter()
        plan_svc.generate_plan(tuples)
        sample.record(time.perf_counter() - start)
    return sample


async def benchmark_parallel_assessment(
    vms: list[VMSummary],
    max_concurrency: int = 10,
    repeat: int = 3,
) -> LatencySample:
    compat_svc = VMwareCompatibilityService()
    factory = MockOpenStackFactory()
    from app.services.vmware.mapping_engine import VMwareMappingEngine

    engine = VMwareMappingEngine(factory)

    # Build a mock inventory service that returns our pre-built VMs
    _vm_map = {vm.id: vm for vm in vms}

    class _MockInventory:
        def get_vm(self, vm_id: str) -> VMSummary | None:
            return _vm_map.get(vm_id)

        def list_vms(self, use_cache: bool = True) -> Any:
            from app.schemas.vmware.inventory import VMListResponse

            return VMListResponse(items=vms)

    from app.services.vmware.parallel_assessment import ParallelAssessmentService

    parallel_svc = ParallelAssessmentService(
        inventory_service=_MockInventory(),  # type: ignore[arg-type]
        compatibility_service=compat_svc,
        mapping_engine=engine,
    )

    sample = LatencySample(f"Parallel (concurrency={max_concurrency})")
    vm_ids = [vm.id for vm in vms]
    for _ in range(repeat):
        start = time.perf_counter()
        progress = await parallel_svc.assess_parallel(
            vm_ids=vm_ids,
            include_mapping=True,
            max_concurrency=max_concurrency,
            timeout_seconds=60,
        )
        elapsed = time.perf_counter() - start
        sample.record(elapsed)
        # Verify all completed
        assert progress.completed + progress.failed == progress.total_vms, (
            f"Expected {progress.total_vms} results, "
            f"got completed={progress.completed} failed={progress.failed}"
        )
    return sample


# ===================================================================
#  Report generation
# ===================================================================

REPORT_HEADER = """# VMware Assessment Benchmark Results

> Generated: {timestamp}
> Environment: {cpu_info}
> Memory: {mem_info}

## Summary

| VM Count | Compatibility | Mapping (cold) | Mapping (warm) | Plan Generation | Parallel (concurrency=10) |
|----------|:-------------:|:--------------:|:--------------:|:---------------:|:-------------------------:|
"""

PER_VM_HEADER = """
## {vm_count} VMs — Detail

### Latency (ms)

| Operation | Avg | p50 | p95 | p99 | Min | Max | Throughput |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---------:|
"""

COLD_VS_WARM_HEADER = """
### Cold Cache vs Warm Cache — Inventory + Mapping

| Cache State | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
|-------------|:--------:|:--------:|:--------:|:--------:|
"""

MEM_FOOTER = """
### Memory Profile

| Metric | Value |
|--------|:-----:|
| RSS Before | {before:.1f} MB |
| RSS After  | {after:.1f} MB |
| Delta      | {delta:+.1f} MB |
"""

COMPAT_NOTE = """
---

## API Compatibility Note

**Breaking change**: The `/api/v1/vmware/assess/{vm_id}/compatibility` endpoint
previously returned `VMCompatibilityResult` with flat boolean fields
(`os_supported`, `cpu_compatible`, `memory_compatible`, `disk_compatible`,
`network_compatible`, `power_state`). It now returns `ScoredCompatibilityResult`
with:

- `score` (float 0.0–1.0) — composite compatibility score
- `issues` (list of `{severity, category, message, compatible}`) — detailed
  per-check results
- `summary` — human-readable one-liner

Old clients consuming the flat fields must migrate to the new `issues[]` format.
The `VMCompatibilityResult` model is preserved in the schema module for
backward-reference but is no longer used by any endpoint.
"""


def _cpu_info() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "unknown"


def _mem_total_gb() -> str:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    return f"{kb / (1024 * 1024):.1f} GB"
    except Exception:
        pass
    return "unknown"


def _generate_report(runs: list[BenchmarkRun]) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        REPORT_HEADER.format(
            timestamp=ts,
            cpu_info=_cpu_info(),
            mem_info=f"{_mem_total_gb()} total",
        ),
    ]

    # Summary table
    for run in runs:
        n = run.vm_count
        compat = run.results.get("Compatibility Check", LatencySample(""))
        mapping_cold = run.results.get("Resource Mapping", LatencySample(""))
        mapping_warm = run.results.get(
            "Resource Mapping (warm cache)", LatencySample("")
        )
        plan = run.results.get("Plan Generation", LatencySample(""))
        parallel = run.results.get("Parallel (concurrency=10)", LatencySample(""))
        lines.append(
            f"| {n:<8d} | {compat.avg_ms:>8.2f} ms |"
            f" {mapping_cold.avg_ms:>8.2f} ms | {mapping_warm.avg_ms:>8.2f} ms |"
            f" {plan.avg_ms:>8.2f} ms | {parallel.avg_ms:>8.2f} ms |\n"
        )

    # Detail per VM size
    for run in runs:
        lines.append(PER_VM_HEADER.format(vm_count=run.vm_count))
        for name, sample in sorted(run.results.items()):
            tput = sample.throughput(run.vm_count)
            lines.append(
                f"| {name:<45s} | {sample.avg_ms:>8.2f} |"
                f" {sample.p50_ms:>8.2f} | {sample.p95_ms:>8.2f} |"
                f" {sample.p99_ms:>8.2f} | {sample.min_ms:>8.2f} |"
                f" {sample.max_ms:>8.2f} | {tput:>8.1f} VM/s |\n"
            )

        lines.append(
            MEM_FOOTER.format(
                before=run.mem_before_mb,
                after=run.mem_after_mb,
                delta=run.mem_after_mb - run.mem_before_mb,
            )
        )

    lines.append(COMPAT_NOTE)
    return "".join(lines)


def _generate_json(runs: list[BenchmarkRun]) -> dict[str, Any]:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "cpu": _cpu_info(),
        "memory_total": _mem_total_gb(),
        "runs": [
            {
                "vm_count": r.vm_count,
                "mem_before_mb": round(r.mem_before_mb, 1),
                "mem_after_mb": round(r.mem_after_mb, 1),
                "results": {
                    name: {
                        "avg_ms": s.avg_ms,
                        "p50_ms": s.p50_ms,
                        "p95_ms": s.p95_ms,
                        "p99_ms": s.p99_ms,
                        "min_ms": s.min_ms,
                        "max_ms": s.max_ms,
                        "count": s.count,
                        "throughput_vm_per_sec": s.throughput(r.vm_count),
                    }
                    for name, s in r.results.items()
                },
            }
            for r in runs
        ],
    }


# ===================================================================
#  Main
# ===================================================================


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="VMware Assessment Benchmark")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    parser.add_argument("--quick", action="store_true", help="Only 10/100 VM sizes")
    parser.add_argument("--warm-only", action="store_true", help="Skip cold-cache")
    args = parser.parse_args()

    sizes = [10, 100] if args.quick else VM_SIZES

    print("=" * 72)
    print("  VMware Migration Assessment — Synthetic Benchmark")
    print(f"  CPU: {_cpu_info()}")
    print(f"  Memory: {_mem_total_gb()} total")
    print(f"  VM sizes: {sizes}")
    print("=" * 72)

    all_runs: list[BenchmarkRun] = []

    for vm_count in sizes:
        print(f"\n{'─' * 72}")
        print(f"  Generating {vm_count} mock VMs...")
        vms = _generate_mock_vms(vm_count)
        print(f"  Done. {len(vms)} VMs created.")

        run = BenchmarkRun(vm_count=vm_count)

        # Memory before
        run.mem_before_mb = _get_rss_mb()

        # --- Compatibility ---
        print(f"  Benchmarking compatibility ({vm_count} VMs)...")
        sample = benchmark_compatibility(vms, repeat=WARM_CACHE_ITERATIONS)
        run.results[sample.name] = sample
        print(
            f"    Avg: {sample.avg_ms:.2f} ms  p50: {sample.p50_ms:.2f} ms  "
            f"p95: {sample.p95_ms:.2f} ms  Throughput: {sample.throughput(vm_count):.1f} VM/s"
        )

        # --- Mapping (cold) ---
        print(f"  Benchmarking mapping — cold cache ({vm_count} VMs)...")
        sample = benchmark_mapping(vms, repeat=WARM_CACHE_ITERATIONS)
        run.results[sample.name] = sample
        print(
            f"    Avg: {sample.avg_ms:.2f} ms  p50: {sample.p50_ms:.2f} ms  "
            f"p95: {sample.p95_ms:.2f} ms"
        )

        # --- Mapping (warm) ---
        print(f"  Benchmarking mapping — warm cache ({vm_count} VMs)...")
        sample = benchmark_mapping_warm(vms, repeat=WARM_CACHE_ITERATIONS)
        run.results[sample.name] = sample
        print(
            f"    Avg: {sample.avg_ms:.2f} ms  p50: {sample.p50_ms:.2f} ms  "
            f"p95: {sample.p95_ms:.2f} ms"
        )

        # --- Plan generation ---
        print(f"  Benchmarking plan generation ({vm_count} VMs)...")
        sample = benchmark_plan_generation(vms, repeat=WARM_CACHE_ITERATIONS)
        run.results[sample.name] = sample
        print(f"    Avg: {sample.avg_ms:.2f} ms  p50: {sample.p50_ms:.2f} ms")

        # --- Parallel assessment ---
        print(f"  Benchmarking parallel assessment ({vm_count} VMs, concurrency=10)...")
        sample = await benchmark_parallel_assessment(vms, max_concurrency=10, repeat=3)
        run.results[sample.name] = sample
        print(
            f"    Avg: {sample.avg_ms:.2f} ms  Throughput: {sample.throughput(vm_count):.1f} VM/s"
        )

        # Memory after
        run.mem_after_mb = _get_rss_mb()

        all_runs.append(run)

    # Generate report
    report = _generate_report(all_runs)

    # Write markdown
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    report_path = docs_dir / "vmware_benchmark_results.md"
    report_path.write_text(report)
    print(f"\n{'─' * 72}")
    print(f"  Report written to {report_path}")

    # Write JSON
    if args.json:
        json_dir = Path("benchmark_results")
        json_dir.mkdir(exist_ok=True)
        json_path = json_dir / "vmware_assessment.json"
        json_path.write_text(
            json.dumps(_generate_json(all_runs), indent=2, default=str)
        )
        print(f"  JSON written to {json_path}")

    print(f"\n{'=' * 72}")
    print("  Benchmark complete.")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    asyncio.run(main())
