#!/usr/bin/env python3
"""Deterministic benchmark inventory generator for VMware assessment validation.

Generates VMware inventory datasets (VMs, datastores, networks, clusters, hosts)
with configurable VM count, scenario mix, and random seed for reproducibility.

Usage
-----
    PYTHONPATH=. python scripts/generate_benchmark_inventory.py --vms 1000 --scenario mixed_compatibility --seed 42
    PYTHONPATH=. python scripts/generate_benchmark_inventory.py --vms 100 --scenario high_risk --seed 7 --json benchmark_data/vmware_inventory_100.json
    PYTHONPATH=. python scripts/generate_benchmark_inventory.py --all  # generate all standard sizes (10,100,500,1000)
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

OS_TEMPLATES: list[dict[str, Any]] = [
    {"os": "CentOS 7",         "family": "linux",   "supported": True},
    {"os": "CentOS 8",         "family": "linux",   "supported": True},
    {"os": "CentOS 9",         "family": "linux",   "supported": True},
    {"os": "Ubuntu 20.04",     "family": "linux",   "supported": True},
    {"os": "Ubuntu 22.04",     "family": "linux",   "supported": True},
    {"os": "Ubuntu 24.04",     "family": "linux",   "supported": True},
    {"os": "Debian 11",        "family": "linux",   "supported": True},
    {"os": "Debian 12",        "family": "linux",   "supported": True},
    {"os": "Red Hat Enterprise Linux 8",  "family": "linux",   "supported": True},
    {"os": "Red Hat Enterprise Linux 9",  "family": "linux",   "supported": True},
    {"os": "SUSE Linux Enterprise Server 15", "family": "linux", "supported": True},
    {"os": "Windows Server 2019",  "family": "windows", "supported": True},
    {"os": "Windows Server 2022",  "family": "windows", "supported": True},
    {"os": "Windows 10",       "family": "windows", "supported": True},
    {"os": "Windows 11",       "family": "windows", "supported": True},
    {"os": "FreeBSD 13",       "family": "unix",    "supported": True},
    {"os": "FreeBSD 14",       "family": "unix",    "supported": True},
    {"os": "Solaris 11",       "family": "unix",    "supported": False},
    {"os": "HP-UX 11i",        "family": "unix",    "supported": False},
    {"os": "macOS Ventura",    "family": "unix",    "supported": False},
]

POWER_STATES = ["poweredOn", "poweredOff", "suspended"]

DISK_CONTROLLER_SETS: list[list[str]] = [
    ["lsilogic"],
    ["lsilogic", "ide"],
    ["pvscsi"],
    ["nvme"],
    ["lsilogic", "nvme"],
    ["pvscsi", "nvme"],
    ["ide"],
    ["sata"],
    ["lsilogic", "sata"],
    [],
]

NIC_TYPES = ["vmxnet3", "e1000", "vmxnet2", "sriov", "e1000e", "unknown"]

FIRMWARE_TYPES = ["bios", "efi"]

DATASTORE_NAMES = [
    "datastore1", "datastore2", "datastore3", "datastore4", "datastore5",
    "vsanDatastore", "nfsDatastore", "ssdDatastore", "localDatastore",
]

NETWORK_NAMES = [
    "VM Network", "Management Network", "Storage Network",
    "vMotion Network", "Public Network", "Private Network",
    "DMZ Network", "iSCSI Network",
]

CLUSTER_NAMES = [
    "Compute-Cluster", "GPU-Cluster", "Management-Cluster",
    "Storage-Cluster", "DR-Cluster",
]

HOST_NAMES = [
    "esxi-01.local", "esxi-02.local", "esxi-03.local", "esxi-04.local",
    "esxi-05.local", "esxi-06.local", "esxi-07.local", "esxi-08.local",
]


# ---------------------------------------------------------------------------
# Scenario configurations
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, float]] = {
    "normal": {
        "linux_pct": 0.60, "windows_pct": 0.30, "unsupported_os_pct": 0.10,
        "efi_pct": 0.15, "secure_boot_pct": 0.05,
        "suspended_pct": 0.05, "multi_disk_pct": 0.50, "multi_nic_pct": 0.40,
        "e1000_nic_pct": 0.20, "legacy_controller_pct": 0.15,
        "tools_ok_pct": 0.85, "no_tools_pct": 0.15,
    },
    "mixed_compatibility": {
        "linux_pct": 0.45, "windows_pct": 0.25, "unsupported_os_pct": 0.30,
        "efi_pct": 0.40, "secure_boot_pct": 0.25,
        "suspended_pct": 0.10, "multi_disk_pct": 0.60, "multi_nic_pct": 0.50,
        "e1000_nic_pct": 0.35, "legacy_controller_pct": 0.30,
        "tools_ok_pct": 0.60, "no_tools_pct": 0.40,
    },
    "high_risk": {
        "linux_pct": 0.20, "windows_pct": 0.20, "unsupported_os_pct": 0.60,
        "efi_pct": 0.70, "secure_boot_pct": 0.50,
        "suspended_pct": 0.25, "multi_disk_pct": 0.70, "multi_nic_pct": 0.60,
        "e1000_nic_pct": 0.50, "legacy_controller_pct": 0.50,
        "tools_ok_pct": 0.30, "no_tools_pct": 0.70,
    },
    "large_scale": {
        "linux_pct": 0.55, "windows_pct": 0.30, "unsupported_os_pct": 0.15,
        "efi_pct": 0.20, "secure_boot_pct": 0.10,
        "suspended_pct": 0.05, "multi_disk_pct": 0.60, "multi_nic_pct": 0.50,
        "e1000_nic_pct": 0.15, "legacy_controller_pct": 0.10,
        "tools_ok_pct": 0.80, "no_tools_pct": 0.20,
    },
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class BenchmarkInventoryGenerator:
    """Deterministic generator for VMware benchmark inventory datasets."""

    def __init__(self, seed: int = 42, scenario: str = "normal"):
        self.rand = random.Random(seed)
        self.seed = seed
        self.scenario_name = scenario
        cfg = SCENARIOS.get(scenario, SCENARIOS["normal"])
        self.cfg = cfg

    def _pick(self, items: list[Any], p: float | None = None) -> Any:
        if p is not None and self.rand.random() < p:
            return items[0]
        return self.rand.choice(items)

    def _bool_with_prob(self, prob: float) -> bool:
        return self.rand.random() < prob

    def _pick_os(self) -> dict[str, Any]:
        r = self.rand.random()
        if r < self.cfg["unsupported_os_pct"]:
            candidates = [t for t in OS_TEMPLATES if not t["supported"]]
        elif r < self.cfg["unsupported_os_pct"] + self.cfg["linux_pct"]:
            candidates = [t for t in OS_TEMPLATES if t["family"] == "linux"]
        else:
            candidates = [t for t in OS_TEMPLATES if t["family"] == "windows"]
        return self.rand.choice(candidates)

    def _generate_vm(self, vm_index: int) -> dict[str, Any]:
        os_info = self._pick_os()
        power = self._pick(POWER_STATES, self.cfg["suspended_pct"])
        firmware = self._pick(FIRMWARE_TYPES, self.cfg["efi_pct"])
        secure_boot = self._bool_with_prob(self.cfg["secure_boot_pct"]) if firmware == "efi" else False

        tools_ok = self._bool_with_prob(self.cfg["tools_ok_pct"])
        tools_status = "toolsOk" if tools_ok else self.rand.choice(["toolsNotRunning", "toolsNotInstalled", None])

        cpu_count = self.rand.randint(1, 32)
        if self.rand.random() < 0.02:
            cpu_count = 0
        memory_mb = self.rand.choice([512, 1024, 2048, 4096, 8192, 16384, 32768, 65536])
        if self.rand.random() < 0.02:
            memory_mb = 0

        num_disks = self.rand.randint(1, 8) if self._bool_with_prob(self.cfg["multi_disk_pct"]) else 1
        if self.rand.random() < 0.03:
            num_disks = 0
        controller_set = self.rand.choice(DISK_CONTROLLER_SETS)
        # Inject legacy controller with configured probability
        if self._bool_with_prob(self.cfg["legacy_controller_pct"]) and "ide" not in controller_set:
            controller_set = list(set(controller_set + ["ide"]))

        disks = []
        for j in range(num_disks):
            capacity_gb = self.rand.choice([10, 20, 40, 80, 100, 250, 500, 1000, 2000])
            disk_type = self.rand.choice(["thin", "thick", "thick", "thin"])
            if self.rand.random() < 0.15:
                disk_type = "thick"
            disks.append({
                "label": f"disk{j}",
                "capacity_gb": capacity_gb,
                "datastore": self.rand.choice(DATASTORE_NAMES),
                "controller_type": self.rand.choice(controller_set) if controller_set else "scsi",
                "disk_type": disk_type,
            })

        num_nics = self.rand.randint(1, 4) if self._bool_with_prob(self.cfg["multi_nic_pct"]) else 1
        nics = []
        for j in range(num_nics):
            nic_type = self.rand.choice(NIC_TYPES)
            if nic_type == "e1000" and self.rand.random() > self.cfg["e1000_nic_pct"]:
                nic_type = "vmxnet3"
            nics.append({
                "label": f"nic{j}",
                "mac": f"00:50:56:{self.rand.randint(0,255):02x}:{j:02x}:{self.rand.randint(0,255):02x}",
                "network": self.rand.choice(NETWORK_NAMES),
                "nic_type": nic_type,
            })

        vm_name = f"vm-{vm_index:05d}-{os_info['os'][:10].replace(' ', '-')}"

        return {
            "id": f"vm-{vm_index:05d}",
            "name": vm_name,
            "power_state": power,
            "guest_os": os_info["os"],
            "os_family": os_info["family"],
            "os_supported": os_info["supported"],
            "hardware": {
                "cpu_count": cpu_count,
                "memory_mb": memory_mb,
                "disks": disks,
                "nics": nics,
            },
            "firmware": firmware,
            "secure_boot_enabled": secure_boot,
            "vmware_tools_status": tools_status,
            "disk_controller_types": controller_set,
            "cluster": self.rand.choice(CLUSTER_NAMES),
            "host": self.rand.choice(HOST_NAMES),
        }

    def generate_inventory(self, vm_count: int) -> dict[str, Any]:
        vms = [self._generate_vm(i) for i in range(vm_count)]

        datastores = [
            {"id": f"ds-{i:02d}", "name": name, "capacity_gb": self.rand.choice([1000, 2000, 4000, 8000, 16000]),
             "free_gb": self.rand.randint(100, 2000), "type": self.rand.choice(["VMFS", "NFS", "vSAN"])}
            for i, name in enumerate(DATASTORE_NAMES)
        ]

        networks = [
            {"id": f"net-{i:02d}", "name": name, "type": self.rand.choice(["standard", "distributed"]),
             "vlan_id": self.rand.randint(1, 4094) if self.rand.random() > 0.3 else None}
            for i, name in enumerate(NETWORK_NAMES)
        ]

        clusters = [
            {"id": f"cl-{i:02d}", "name": name, "host_count": self.rand.randint(2, 8),
             "total_cpu_ghz": round(self.rand.uniform(50, 500), 1),
             "total_mem_gb": self.rand.randint(256, 2048)}
            for i, name in enumerate(CLUSTER_NAMES)
        ]

        hosts = [
            {"id": f"host-{i:02d}", "name": name, "cluster": self.rand.choice(CLUSTER_NAMES),
             "cpu_cores": self.rand.choice([16, 24, 32, 48, 64]),
             "memory_gb": self.rand.choice([128, 256, 512, 1024]),
             "vm_count": self.rand.randint(5, 50)}
            for i, name in enumerate(HOST_NAMES)
        ]

        return {
            "generator": {
                "script": "generate_benchmark_inventory.py",
                "seed": self.seed,
                "scenario": self.scenario_name,
                "generated_at": datetime.utcnow().isoformat(),
            },
            "summary": {
                "vm_count": len(vms),
                "datastore_count": len(datastores),
                "network_count": len(networks),
                "cluster_count": len(clusters),
                "host_count": len(hosts),
                "linux_vms": sum(1 for v in vms if v["os_family"] == "linux"),
                "windows_vms": sum(1 for v in vms if v["os_family"] == "windows"),
                "unsupported_os_vms": sum(1 for v in vms if not v["os_supported"]),
                "uefi_vms": sum(1 for v in vms if v["firmware"] == "efi"),
                "secure_boot_vms": sum(1 for v in vms if v["secure_boot_enabled"]),
                "suspended_vms": sum(1 for v in vms if v["power_state"] == "suspended"),
                "no_tools_vms": sum(1 for v in vms if v["vmware_tools_status"] not in ("toolsOk", None)),
            },
            "datastores": datastores,
            "networks": networks,
            "clusters": clusters,
            "hosts": hosts,
            "vms": vms,
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate benchmark inventory datasets")
    parser.add_argument("--vms", type=int, default=None, help="Number of VMs to generate")
    parser.add_argument("--scenario", type=str, default="normal",
                        choices=list(SCENARIOS.keys()), help="Scenario mix")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--json", type=str, default=None, help="Output JSON file path")
    parser.add_argument("--all", action="store_true", help="Generate all standard sizes (10,100,500,1000,5000)")
    args = parser.parse_args()

    output_dir = Path("benchmark_data")
    output_dir.mkdir(exist_ok=True)

    if args.all:
        sizes = [10, 100, 500, 1000, 5000]
        scenarios = ["normal", "mixed_compatibility", "high_risk"]
        for size in sizes:
            for scenario in scenarios:
                gen = BenchmarkInventoryGenerator(seed=args.seed, scenario=scenario)
                inventory = gen.generate_inventory(size)
                path = output_dir / f"vmware_inventory_{size}_{scenario}.json"
                path.write_text(json.dumps(inventory, indent=2))
                print(f"  Generated: {path} ({size} VMs, {scenario})")
        # Also generate default names (normal scenario)
        for size in sizes:
            gen = BenchmarkInventoryGenerator(seed=args.seed, scenario="normal")
            inventory = gen.generate_inventory(size)
            path = output_dir / f"vmware_inventory_{size}.json"
            path.write_text(json.dumps(inventory, indent=2))
            print(f"  Generated: {path} ({size} VMs, normal)")
    else:
        vm_count = args.vms or 100
        gen = BenchmarkInventoryGenerator(seed=args.seed, scenario=args.scenario)
        inventory = gen.generate_inventory(vm_count)

        output_path = args.json or str(output_dir / f"vmware_inventory_{vm_count}.json")
        Path(output_path).write_text(json.dumps(inventory, indent=2))

        s = inventory["summary"]
        print(f"Generated: {output_path}")
        print(f"  VMs: {s['vm_count']} (Linux: {s['linux_vms']}, Windows: {s['windows_vms']}, "
              f"Unsupported OS: {s['unsupported_os_vms']})")
        print(f"  UEFI: {s['uefi_vms']}, Secure Boot: {s['secure_boot_vms']}, "
              f"Suspended: {s['suspended_vms']}, No Tools: {s['no_tools_vms']}")
        print(f"  Datastores: {s['datastore_count']}, Networks: {s['network_count']}, "
              f"Clusters: {s['cluster_count']}, Hosts: {s['host_count']}")


if __name__ == "__main__":
    main()
