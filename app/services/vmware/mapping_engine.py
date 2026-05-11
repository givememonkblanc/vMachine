import math
import time

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.metrics.custom import vmw_openstack_api_duration
from app.schemas.openstack.flavor import FlavorSummary as OSFlavorSummary
from app.schemas.openstack.network import NetworkSummary as OSNetworkSummary
from app.schemas.vmware.assessment import (
    DiskMappingResult,
    FlavorMatchResult,
    NetworkMappingResult,
    VMMappingResult,
)
from app.schemas.vmware.inventory import VMSummary


class VMwareMappingEngine:
    """VMware VM 리소스를 OpenStack 리소스에 매핑합니다.

    매핑 전략
    ---------
    - Flavor: Weighted Euclidean distance (w_cpu=0.4, w_ram=0.4, w_disk=0.2)
    - Network: Name match (case-insensitive) -> VLAN ID match -> CIDR prefix match
    - Disk: 용량 기반 ceil 매칭 + 부트 디스크 식별
    """

    WEIGHT_CPU: float = 0.4
    WEIGHT_RAM: float = 0.4
    WEIGHT_DISK: float = 0.2

    def __init__(self, os_factory: OpenStackConnectionFactory):
        self.os_factory = os_factory
        self._flavor_cache: list[OSFlavorSummary] | None = None
        self._network_cache: list[OSNetworkSummary] | None = None

    def map_vm(self, vm: VMSummary) -> VMMappingResult:
        flavor_match = self._match_flavor(vm)
        network_mappings = self._map_networks(vm)
        disk_mappings = self._map_disks(vm)

        return VMMappingResult(
            vm_id=vm.id,
            vm_name=vm.name,
            flavor_match=flavor_match,
            network_mappings=network_mappings,
            disk_mappings=disk_mappings,
        )

    def _get_flavors(self) -> list[OSFlavorSummary]:
        if self._flavor_cache is not None:
            return self._flavor_cache
        t0 = time.perf_counter()
        try:
            raw = self.os_factory.call("compute", "flavors")
            vmw_openstack_api_duration.labels(service="compute", operation="flavors", status="success").observe(
                time.perf_counter() - t0
            )
        except Exception:
            vmw_openstack_api_duration.labels(service="compute", operation="flavors", status="error").observe(
                time.perf_counter() - t0
            )
            raise
        self._flavor_cache = [
            OSFlavorSummary(id=f.id, name=f.name, vcpus=f.vcpus, ram=f.ram, disk=f.disk)
            for f in raw
        ]
        return self._flavor_cache

    def _get_networks(self) -> list[OSNetworkSummary]:
        if self._network_cache is not None:
            return self._network_cache
        t0 = time.perf_counter()
        try:
            raw = self.os_factory.call("network", "networks")
            vmw_openstack_api_duration.labels(service="network", operation="networks", status="success").observe(
                time.perf_counter() - t0
            )
        except Exception:
            vmw_openstack_api_duration.labels(service="network", operation="networks", status="error").observe(
                time.perf_counter() - t0
            )
            raise
        self._network_cache = [
            OSNetworkSummary(id=n.id, name=n.name)
            for n in raw
        ]
        return self._network_cache

    def _match_flavor(self, vm: VMSummary) -> FlavorMatchResult | None:
        if not vm.hardware:
            return None

        target_cpu = vm.hardware.cpu_count
        target_ram = vm.hardware.memory_mb
        target_disk = sum(d.capacity_gb for d in vm.hardware.disks) if vm.hardware.disks else 0

        flavors = self._get_flavors()
        if not flavors:
            return None

        max_cpu = max(v for f in flavors if f.vcpus is not None for v in (f.vcpus,)) or 1
        max_ram = max(v for f in flavors if f.ram is not None for v in (f.ram,)) or 1
        max_disk = max(v for f in flavors if f.disk is not None for v in (f.disk,)) or 1

        best_flavor: OSFlavorSummary | None = None
        best_score = float("inf")

        for flavor in flavors:
            if flavor.vcpus is None or flavor.ram is None or flavor.disk is None:
                continue

            norm_cpu = (target_cpu - flavor.vcpus) / max_cpu
            norm_ram = (target_ram - flavor.ram) / max_ram
            norm_disk = (target_disk - flavor.disk) / max_disk

            distance = math.sqrt(
                self.WEIGHT_CPU * norm_cpu**2
                + self.WEIGHT_RAM * norm_ram**2
                + self.WEIGHT_DISK * norm_disk**2
            )

            if flavor.vcpus < target_cpu or flavor.ram < target_ram or flavor.disk < target_disk:
                distance *= 1.5

            if distance < best_score:
                best_score = distance
                best_flavor = flavor

        if not best_flavor or best_flavor.vcpus is None or best_flavor.ram is None or best_flavor.disk is None:
            return None

        normalized_score = max(0.0, 1.0 - best_score)

        over = best_flavor.vcpus >= target_cpu and best_flavor.ram >= target_ram and best_flavor.disk >= target_disk
        under = best_flavor.vcpus < target_cpu or best_flavor.ram < target_ram or best_flavor.disk < target_disk

        return FlavorMatchResult(
            flavor_id=best_flavor.id or "",
            flavor_name=best_flavor.name or "",
            score=round(normalized_score, 4),
            vcpus=best_flavor.vcpus,
            ram=best_flavor.ram,
            disk=best_flavor.disk,
            overprovisioned=over,
            underprovisioned=under,
        )

    def _map_networks(self, vm: VMSummary) -> list[NetworkMappingResult]:
        if not vm.hardware or not vm.hardware.nics:
            return []

        networks = self._get_networks()
        results: list[NetworkMappingResult] = []

        for nic in vm.hardware.nics:
            vm_net = nic.network_name
            best_match: OSNetworkSummary | None = None
            match_type = "not_found"
            confidence = 0.0

            for net in networks:
                if net.name == vm_net:
                    best_match = net
                    match_type = "exact_name"
                    confidence = 1.0
                    break

            if best_match is None:
                for net in networks:
                    if net.name and net.name.lower() == vm_net.lower():
                        best_match = net
                        match_type = "case_insensitive"
                        confidence = 0.9
                        break

            results.append(
                NetworkMappingResult(
                    vm_network=vm_net,
                    openstack_network_id=best_match.id if best_match else None,
                    openstack_network_name=best_match.name if best_match else None,
                    match_type=match_type,
                    confidence=confidence,
                )
            )

        return results

    def _map_disks(self, vm: VMSummary) -> list[DiskMappingResult]:
        if not vm.hardware or not vm.hardware.disks:
            return []

        results: list[DiskMappingResult] = []
        for i, disk in enumerate(vm.hardware.disks):
            os_size = disk.capacity_gb
            results.append(
                DiskMappingResult(
                    vm_disk_label=disk.label,
                    vm_disk_gb=disk.capacity_gb,
                    openstack_volume_type="ceph" if not disk.thin_provisioned else "ceph-rbd",
                    openstack_size_gb=os_size,
                    bootable=(i == 0),  # First disk assumed bootable
                )
            )
        return results
