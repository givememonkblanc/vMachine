#!/usr/bin/env python3
"""Concurrency sweep benchmark — tests parallel assessment at multiple concurrency levels.

Measures p50/p95/p99 latency, throughput (VM/sec), memory, and CPU usage
for concurrency levels 1, 5, 10, 20 on 1000 and 5000 VM datasets.

Usage:
    PYTHONPATH=. python scripts/concurrency_sweep.py
    PYTHONPATH=. python scripts/concurrency_sweep.py --json
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ["APP_ENV"] = "benchmark"

from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
from app.services.vmware.compatibility import VMwareCompatibilityService

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class ConcurrencySample:
    concurrency: int
    vm_count: int
    durations_ms: list[float] = field(default_factory=list)
    mem_before_mb: float = 0.0
    mem_after_mb: float = 0.0
    cpu_percent: float = 0.0

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.durations_ms) if self.durations_ms else 0.0

    @property
    def p50_ms(self) -> float:
        s = sorted(self.durations_ms)
        return s[len(s) // 2] if s else 0.0

    @property
    def p95_ms(self) -> float:
        s = sorted(self.durations_ms)
        return s[int(len(s) * 0.95)] if s else 0.0

    @property
    def p99_ms(self) -> float:
        s = sorted(self.durations_ms)
        return s[int(len(s) * 0.99)] if s else 0.0

    @property
    def throughput_vms(self) -> float:
        if not self.durations_ms or self.avg_ms <= 0:
            return 0.0
        return self.vm_count / (self.avg_ms / 1000)

    @property
    def min_ms(self) -> float:
        return min(self.durations_ms) if self.durations_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.durations_ms) if self.durations_ms else 0.0


def _rss_mb() -> float:
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    return 0.0


def _cpu_pct() -> float:
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).cpu_percent(interval=0.1)
    return 0.0


def _vm_summary_from_dict(vm_dict: dict[str, Any]) -> VMSummary:
    hw = vm_dict.get("hardware", {})
    disks = [
        VMDisk(
            label=d.get("label", ""),
            capacity_gb=d.get("capacity_gb", 0),
            datastore_name=d.get("datastore"),
            controller_type=d.get("controller_type"),
            thin_provisioned=d.get("disk_type", "thick") != "thick",
        )
        for d in hw.get("disks", [])
    ]
    nics = [
        VMNic(
            label=n.get("label", ""),
            network_name=n.get("network"),
            mac_address=n.get("mac"),
            nic_type=n.get("nic_type"),
        )
        for n in hw.get("nics", [])
    ]
    hardware = VMHardware(cpu_count=hw.get("cpu_count", 0), memory_mb=hw.get("memory_mb", 0), disks=disks, nics=nics)
    return VMSummary(
        id=vm_dict.get("id", ""),
        name=vm_dict.get("name", ""),
        power_state=vm_dict.get("power_state", "poweredOff"),
        guest_os=vm_dict.get("guest_os", ""),
        hardware=hardware,
        firmware=vm_dict.get("firmware"),
        secure_boot_enabled=vm_dict.get("secure_boot_enabled"),
        vmware_tools_status=vm_dict.get("vmware_tools_status"),
        disk_controller_types=vm_dict.get("disk_controller_types", []),
    )


async def benchmark_parallel(
    vms: list[VMSummary],
    concurrency: int,
    repeat: int = 5,
) -> ConcurrencySample:
    svc = VMwareCompatibilityService()
    sample = ConcurrencySample(concurrency=concurrency, vm_count=len(vms))
    sample.mem_before_mb = _rss_mb()

    async def _eval_one(vm: VMSummary) -> None:
        svc.evaluate(vm)

    for _ in range(repeat):
        sem = asyncio.Semaphore(concurrency)

        async def _limited(vm: VMSummary) -> None:
            async with sem:
                return await _eval_one(vm)

        start = time.perf_counter()
        await asyncio.gather(*[_limited(vm) for vm in vms])
        elapsed = (time.perf_counter() - start) * 1000
        sample.durations_ms.append(elapsed)

    sample.mem_after_mb = _rss_mb()
    sample.cpu_percent = _cpu_pct()
    return sample


def load_dataset(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inventory = json.loads(Path(path).read_text())
    vms = inventory.get("vms", [])
    summary = inventory.get("summary", {})
    return vms, summary


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Concurrency Sweep Benchmark")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    parser.add_argument("--data-dir", type=str, default="benchmark_data",
                        help="Directory containing inventory datasets")
    args = parser.parse_args()

    datasets = [1000, 5000]
    concurrency_levels = [1, 5, 10, 20]
    repeat = 5

    print("=" * 72)
    print("  Concurrency Sweep Benchmark")
    print(f"  Datasets: {datasets}")
    print(f"  Concurrency levels: {concurrency_levels}")
    print(f"  Repeats per level: {repeat}")
    print(f"  Memory: {_rss_mb():.1f} MB (current)")
    print("=" * 72)

    all_results: list[dict[str, Any]] = []

    for size in datasets:
        path = Path(args.data_dir) / f"vmware_inventory_{size}.json"
        print(f"\n{'─' * 72}")
        print(f"  Dataset: {path} ({size} VMs)")
        vm_dicts, summary = load_dataset(str(path))
        vms = [_vm_summary_from_dict(v) for v in vm_dicts]
        print(f"  VMs loaded: {len(vms)}")

        for concurrency in concurrency_levels:
            print(f"\n  → Concurrency={concurrency}...", end=" ", flush=True)
            sample = await benchmark_parallel(vms, concurrency=concurrency, repeat=repeat)
            mem_delta = sample.mem_after_mb - sample.mem_before_mb
            print(
                f"avg={sample.avg_ms:.1f}ms "
                f"p50={sample.p50_ms:.1f}ms "
                f"p95={sample.p95_ms:.1f}ms "
                f"p99={sample.p99_ms:.1f}ms "
                f"throughput={sample.throughput_vms:.0f} VM/s "
                f"mem_delta={mem_delta:+.1f}MB"
            )

            all_results.append({
                "vm_count": size,
                "concurrency": concurrency,
                "avg_ms": round(sample.avg_ms, 2),
                "p50_ms": round(sample.p50_ms, 2),
                "p95_ms": round(sample.p95_ms, 2),
                "p99_ms": round(sample.p99_ms, 2),
                "min_ms": round(sample.min_ms, 2),
                "max_ms": round(sample.max_ms, 2),
                "throughput_vm_per_s": round(sample.throughput_vms, 0),
                "mem_before_mb": round(sample.mem_before_mb, 1),
                "mem_after_mb": round(sample.mem_after_mb, 1),
                "mem_delta_mb": round(mem_delta, 1),
                "cpu_percent": round(sample.cpu_percent, 1),
                "durations_ms": [round(d, 2) for d in sample.durations_ms],
            })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": all_results,
    }

    output_dir = Path("benchmark_results") / "scaling"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "concurrency_sweep.json"
    json_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nJSON: {json_path}")

    print(f"\n{'=' * 72}")
    print("  Summary Table")
    print(f"{'=' * 72}")
    print(f"{'VMs':>6} | {'Concurrency':>11} | {'Avg (ms)':>9} | {'p50 (ms)':>9} | {'p95 (ms)':>9} | {'p99 (ms)':>9} | {'VM/s':>6} | {'Mem Δ':>6}")
    print("-" * 72)
    for r in all_results:
        print(
            f"{r['vm_count']:>6} | {r['concurrency']:>11} | "
            f"{r['avg_ms']:>9.1f} | {r['p50_ms']:>9.1f} | {r['p95_ms']:>9.1f} | "
            f"{r['p99_ms']:>9.1f} | {r['throughput_vm_per_s']:>6.0f} | "
            f"{r['mem_delta_mb']:>+5.1f}"
        )
    print(f"{'=' * 72}")


if __name__ == "__main__":
    asyncio.run(main())
