#!/usr/bin/env python3
"""Dataset-based benchmark runner for VMware assessment engine.

Loads VMware inventory JSON and OpenStack catalog JSON, then runs
compatibility assessment, flavor mapping, network mapping, plan generation,
and parallel assessment against the dataset.

Usage
-----
    PYTHONPATH=. python scripts/benchmark_from_dataset.py \\
        --inventory benchmark_data/vmware_inventory_1000.json \\
        --catalog benchmark_data/openstack_catalog.json

    PYTHONPATH=. python scripts/benchmark_from_dataset.py --all  # run all standard sizes
    PYTHONPATH=. python scripts/benchmark_from_dataset.py --quick --json
"""

from __future__ import annotations

import argparse
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

# Project imports
from app.schemas.vmware.assessment import ScoredCompatibilityResult, VMMappingResult
from app.schemas.vmware.inventory import VMDisk, VMHardware, VMNic, VMSummary
from app.services.vmware.compatibility import VMwareCompatibilityService
from app.services.vmware.plan_service import VMwarePlanService

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DatasetBenchmarkRun:
    name: str
    vm_count: int
    source_file: str
    compatible: int = 0
    incompatible: int = 0
    warning_count: int = 0
    top_incompatibility_reasons: dict[str, int] = field(default_factory=dict)
    mapping_success_rate: float = 0.0
    durations_ms: list[float] = field(default_factory=list)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rss_mb() -> float:
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    return 0.0


def _vm_summary_from_dict(vm_dict: dict[str, Any]) -> VMSummary:
    hw = vm_dict.get("hardware", {})

    disks = []
    for d in hw.get("disks", []):
        disks.append(VMDisk(
            label=d.get("label", ""),
            capacity_gb=d.get("capacity_gb", 0),
            datastore_name=d.get("datastore"),
            controller_type=d.get("controller_type"),
            thin_provisioned=d.get("disk_type", "thick") != "thick",
        ))

    nics = []
    for n in hw.get("nics", []):
        nics.append(VMNic(
            label=n.get("label", ""),
            network_name=n.get("network"),
            mac_address=n.get("mac"),
            nic_type=n.get("nic_type"),
        ))

    hardware = VMHardware(
        cpu_count=hw.get("cpu_count", 0),
        memory_mb=hw.get("memory_mb", 0),
        disks=disks,
        nics=nics,
    )
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


def _validate_dataset(inventory: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    vms = inventory.get("vms", [])
    if not vms:
        warnings.append("No VMs found in inventory dataset")
    for i, vm in enumerate(vms):
        if "id" not in vm:
            warnings.append(f"VM at index {i} missing 'id'")
        if "hardware" not in vm:
            warnings.append(f"VM {vm.get('id', i)} missing 'hardware'")
        hw = vm.get("hardware", {})
        if "disks" not in hw:
            warnings.append(f"VM {vm.get('id', i)} hardware missing 'disks'")
        if "nics" not in hw:
            warnings.append(f"VM {vm.get('id', i)} hardware missing 'nics'")
    return warnings


# ---------------------------------------------------------------------------
# Benchmark functions
# ---------------------------------------------------------------------------

def benchmark_compatibility(vm_dicts: list[dict[str, Any]],
                            repeat: int = 3) -> DatasetBenchmarkRun:
    svc = VMwareCompatibilityService()
    vms = [_vm_summary_from_dict(v) for v in vm_dicts]
    run = DatasetBenchmarkRun(
        name="Compatibility Check", vm_count=len(vm_dicts),
        source_file="dataset"
    )

    for _ in range(repeat):
        start = time.perf_counter()
        all_results: list[ScoredCompatibilityResult] = []
        for vm in vms:
            result = svc.evaluate(vm)
            all_results.append(result)
        elapsed = (time.perf_counter() - start) * 1000
        run.durations_ms.append(elapsed)

    # Analyze results
    for result in all_results:
        if result.compatible:
            run.compatible += 1
        else:
            run.incompatible += 1
        for issue in result.issues:
            if not issue.compatible:
                reason = f"{issue.severity}: {issue.category} — {issue.message[:60]}"
                run.top_incompatibility_reasons[reason] = \
                    run.top_incompatibility_reasons.get(reason, 0) + 1
        run.warning_count += len([i for i in result.issues if i.severity in ("low", "medium", "high")])

    # Sort top incompatibility reasons
    run.top_incompatibility_reasons = dict(
        sorted(run.top_incompatibility_reasons.items(),
               key=lambda x: -x[1])[:10]
    )
    return run


def benchmark_mapping(vm_dicts: list[dict[str, Any]],
                      catalog: dict[str, Any],
                      repeat: int = 3) -> DatasetBenchmarkRun:
    """Simulate mapping by computing flavor match for each VM."""
    from app.services.vmware.mapping_engine import VMwareMappingEngine
    from scripts.benchmark_vmware_assessment import MockOpenStackFactory

    factory = MockOpenStackFactory()
    engine = VMwareMappingEngine(factory)
    vms = [_vm_summary_from_dict(v) for v in vm_dicts]
    run = DatasetBenchmarkRun(
        name="Resource Mapping", vm_count=len(vm_dicts),
        source_file="dataset"
    )

    for _ in range(repeat):
        start = time.perf_counter()
        for vm in vms:
            engine.map_vm(vm)
        elapsed = (time.perf_counter() - start) * 1000
        run.durations_ms.append(elapsed)

    # Run once more for detailed analysis
    mapping_count = 0
    for vm in vms:
        try:
            result = engine.map_vm(vm)
            mapping_count += 1 if result else 0
        except Exception:
            pass
    run.mapping_success_rate = (mapping_count / len(vms) * 100) if vms else 0.0
    return run


def benchmark_plan_generation(vm_dicts: list[dict[str, Any]],
                              repeat: int = 2) -> DatasetBenchmarkRun:
    svc = VMwareCompatibilityService()
    plan_svc = VMwarePlanService()
    vms = [_vm_summary_from_dict(v) for v in vm_dicts]
    run = DatasetBenchmarkRun(
        name="Plan Generation", vm_count=len(vm_dicts),
        source_file="dataset"
    )

    for _ in range(repeat):
        results_list = [(vm, svc.evaluate(vm), None) for vm in vms]
        start = time.perf_counter()
        plan_svc.generate_plan(results_list)
        elapsed = (time.perf_counter() - start) * 1000
        run.durations_ms.append(elapsed)
    return run


async def benchmark_parallel(vm_dicts: list[dict[str, Any]],
                             concurrency: int = 10,
                             repeat: int = 2) -> DatasetBenchmarkRun:
    svc = VMwareCompatibilityService()
    vms = [_vm_summary_from_dict(v) for v in vm_dicts]
    run = DatasetBenchmarkRun(
        name=f"Parallel Assessment (concurrency={concurrency})",
        vm_count=len(vm_dicts), source_file="dataset"
    )

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
        run.durations_ms.append(elapsed)
    return run


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(all_runs: list[DatasetBenchmarkRun], catalog: dict[str, Any],
                    dataset_path: str, warnings: list[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# Dataset Benchmark Report",
        f"",
        f"> Generated: {now}",
        f"> Dataset: {dataset_path}",
        f"> OpenStack catalog: {catalog.get('catalog', {}).get('name', 'unknown')}",
        f"> Memory: {_rss_mb():.0f} MB RSS",
        f"",
        f"## Validation Warnings",
    ]
    if warnings:
        for w in warnings:
            lines.append(f"- ⚠️ {w}")
    else:
        lines.append(f"- ✅ No validation warnings")

    lines.extend([
        f"",
        f"## Summary",
        f"",
        f"| Operation | VMs | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Compatible | Incompatible | Mapping Rate |",
        f"|-----------|:---:|:--------:|:--------:|:--------:|:--------:|:----------:|:------------:|:------------:|",
    ])

    for run in all_runs:
        compat_str = str(run.compatible) if run.compatible > 0 else "-"
        incompat_str = str(run.incompatible) if run.incompatible > 0 else "-"
        map_str = f"{run.mapping_success_rate:.0f}%" if run.mapping_success_rate else "-"
        lines.append(
            f"| {run.name} | {run.vm_count} | {run.avg_ms:.2f} | {run.p50_ms:.2f} | "
            f"{run.p95_ms:.2f} | {run.p99_ms:.2f} | {compat_str} | {incompat_str} | {map_str} |"
        )

    # Top incompatibility reasons
    compat_runs = [r for r in all_runs if r.top_incompatibility_reasons]
    if compat_runs:
        lines.extend([
            f"",
            f"## Top Incompatibility Reasons",
            f"",
            f"| Reason | Count |",
            f"|--------|:-----:|",
        ])
        for run in compat_runs:
            for reason, count in list(run.top_incompatibility_reasons.items())[:5]:
                lines.append(f"| {reason} | {count} |")

    lines.extend([
        f"",
        f"## Notes",
        f"",
        f"- Dataset-based benchmarks include Pydantic deserialization overhead (JSON → VMSummary)",
        f"- Mapping uses in-process Euclidean distance — no live OpenStack API calls",
        f"- For live vCenter/OpenStack validation, use scripts/validate_vcenter.py and validate_openstack_mapping.py",
        f"",
        f"---",
        f"*Report generated by benchmark_from_dataset.py*",
    ])
    return "\n".join(lines)


def generate_json(all_runs: list[DatasetBenchmarkRun]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": [
            {
                "name": r.name,
                "vm_count": r.vm_count,
                "avg_ms": round(r.avg_ms, 2),
                "p50_ms": round(r.p50_ms, 2),
                "p95_ms": round(r.p95_ms, 2),
                "p99_ms": round(r.p99_ms, 2),
                "compatible": r.compatible,
                "incompatible": r.incompatible,
                "warning_count": r.warning_count,
                "mapping_success_rate": round(r.mapping_success_rate, 1),
                "top_incompatibility_reasons": r.top_incompatibility_reasons,
            }
            for r in all_runs
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Dataset-based benchmark runner")
    parser.add_argument("--inventory", type=str, default=None, help="Path to inventory JSON")
    parser.add_argument("--catalog", type=str, default="benchmark_data/openstack_catalog.json",
                        help="Path to OpenStack catalog JSON")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    parser.add_argument("--quick", action="store_true", help="Run 10 and 100 only")
    parser.add_argument("--all", action="store_true", help="Run all standard sizes (10,100,500,1000)")
    args = parser.parse_args()

    # Load catalog
    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        print(f"ERROR: Catalog not found: {catalog_path}")
        sys.exit(1)
    catalog = json.loads(catalog_path.read_text())
    print(f"OpenStack catalog: {catalog['catalog']['name']} "
          f"({catalog['summary']['flavor_count']} flavors, "
          f"{catalog['summary']['network_count']} networks)")

    # Determine which datasets to run
    datasets: list[Path] = []
    if args.inventory:
        datasets.append(Path(args.inventory))
    elif args.all:
        base = Path("benchmark_data")
        if args.quick:
            sizes = [10, 100]
        else:
            sizes = [10, 100, 500, 1000]
        for size in sizes:
            p = base / f"vmware_inventory_{size}.json"
            if p.exists():
                datasets.append(p)
    else:
        # Default: run 100 and 1000
        for size in [100, 1000]:
            p = Path(f"benchmark_data/vmware_inventory_{size}.json")
            if p.exists():
                datasets.append(p)

    if not datasets:
        print("ERROR: No inventory datasets found.")
        print("  Run 'python scripts/generate_benchmark_inventory.py --all' first.")
        sys.exit(1)

    all_runs: list[DatasetBenchmarkRun] = []

    for ds_path in datasets:
        print(f"\n{'=' * 60}")
        print(f"Dataset: {ds_path}")
        inventory = json.loads(ds_path.read_text())
        vms = inventory.get("vms", [])
        summary = inventory.get("summary", {})
        print(f"  VMs: {len(vms)} (Linux: {summary.get('linux_vms', '?')}, "
              f"Windows: {summary.get('windows_vms', '?')}, "
              f"Unsupported OS: {summary.get('unsupported_os_vms', '?')})")

        # Validate
        warnings = _validate_dataset(inventory)
        for w in warnings:
            print(f"  ⚠️  {w}")

        # Compatibility
        print(f"  → Compatibility...", end=" ", flush=True)
        run = benchmark_compatibility(vms, repeat=3)
        all_runs.append(run)
        print(f"avg={run.avg_ms:.1f}ms compatible={run.compatible}/{run.vm_count}")

        # Mapping
        print(f"  → Mapping...", end=" ", flush=True)
        run = benchmark_mapping(vms, catalog, repeat=3)
        all_runs.append(run)
        print(f"avg={run.avg_ms:.1f}ms success_rate={run.mapping_success_rate:.0f}%")

        # Plan generation
        print(f"  → Plan generation...", end=" ", flush=True)
        run = benchmark_plan_generation(vms, repeat=2)
        all_runs.append(run)
        print(f"avg={run.avg_ms:.1f}ms")

        # Parallel assessment
        print(f"  → Parallel assessment...", end=" ", flush=True)
        run = await benchmark_parallel(vms, concurrency=10, repeat=2)
        all_runs.append(run)
        print(f"avg={run.avg_ms:.1f}ms")

    # Generate report
    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "dataset_benchmark_report.md"
    report_path.write_text(generate_report(
        all_runs, catalog,
        ", ".join(str(d) for d in datasets),
        warnings if datasets else []
    ))
    print(f"\nReport: {report_path}")

    if args.json:
        json_dir = Path("benchmark_results")
        json_dir.mkdir(exist_ok=True)
        json_path = json_dir / "dataset_benchmark.json"
        json_path.write_text(json.dumps(generate_json(all_runs), indent=2, default=str))
        print(f"JSON:   {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
