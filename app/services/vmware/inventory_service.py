from typing import Any

from app.clients.vmware.connection import VMwareClientFactory
from app.common.utils.cache import TTLCache
from app.db.session.session import SessionLocal
from app.models.resource_snapshot import ResourceSnapshot
from app.schemas.vmware.inventory import (
    DatastoreListResponse,
    DatastoreSummary,
    InventorySyncResponse,
    NetworkListResponse,
    NetworkSummary,
    VMDisk,
    VMHardware,
    VMListResponse,
    VMNic,
    VMSummary,
)


class VMwareInventoryService:
    def __init__(self, vmware_factory: VMwareClientFactory):
        self.factory = vmware_factory
        self._vm_cache: TTLCache[list[VMSummary]] = TTLCache(ttl_seconds=300)
        self._ds_cache: TTLCache[list[DatastoreSummary]] = TTLCache(ttl_seconds=300)
        self._net_cache: TTLCache[list[NetworkSummary]] = TTLCache(ttl_seconds=300)

    def list_vms(self, use_cache: bool = True) -> VMListResponse:
        if use_cache:
            cached = self._vm_cache.get("vms")
            if cached is not None:
                return VMListResponse(items=cached)
        raw_vms = self.factory.list_vms()
        items = [self._build_vm_summary(vm) for vm in raw_vms]
        self._vm_cache.set("vms", items)
        return VMListResponse(items=items)

    def list_datastores(self, use_cache: bool = True) -> DatastoreListResponse:
        if use_cache:
            cached = self._ds_cache.get("datastores")
            if cached is not None:
                return DatastoreListResponse(items=cached)
        raw_ds = self.factory.list_datastores()
        items = [self._build_datastore_summary(ds) for ds in raw_ds]
        self._ds_cache.set("datastores", items)
        return DatastoreListResponse(items=items)

    def list_networks(self, use_cache: bool = True) -> NetworkListResponse:
        if use_cache:
            cached = self._net_cache.get("networks")
            if cached is not None:
                return NetworkListResponse(items=cached)
        raw_nets = self.factory.list_networks()
        items = [self._build_network_summary(net) for net in raw_nets]
        self._net_cache.set("networks", items)
        return NetworkListResponse(items=items)

    def get_vm(self, vm_id: str) -> VMSummary | None:
        items = self.list_vms(use_cache=True).items
        for vm in items:
            if vm.id == vm_id:
                return vm
        return None

    def sync_inventory(self, operation_task_id: str | None = None) -> InventorySyncResponse:
        vms = self.factory.list_vms()
        datastores = self.factory.list_datastores()
        networks = self.factory.list_networks()

        synced_vms = 0
        synced_ds = 0
        synced_net = 0

        for vm in vms:
            detail = self.factory.get_vm_detail(vm)
            self._upsert_snapshot("vmware_vm", vm.id, detail.get("name", ""), detail)
            synced_vms += 1

        for ds in datastores:
            detail = self.factory.get_datastore_detail(ds)
            self._upsert_snapshot("vmware_datastore", ds.id, detail.get("name", ""), detail)
            synced_ds += 1

        for net in networks:
            detail = self.factory.get_network_detail(net)
            self._upsert_snapshot("vmware_network", net.id, detail.get("name", ""), detail)
            synced_net += 1

        # Invalidate in-memory caches so next read picks up fresh data
        self._vm_cache.invalidate_all()
        self._ds_cache.invalidate_all()
        self._net_cache.invalidate_all()

        return InventorySyncResponse(
            synced_vms=synced_vms,
            synced_datastores=synced_ds,
            synced_networks=synced_net,
            operation_task_id=operation_task_id,
        )

    def _upsert_snapshot(self, resource_type: str, external_id: str, resource_name: str, raw_data: dict[str, Any]) -> None:
        import asyncio

        async def _do_upsert():
            async with SessionLocal() as session:
                from sqlalchemy import select
                stmt = select(ResourceSnapshot).where(
                    ResourceSnapshot.resource_type == resource_type,
                    ResourceSnapshot.external_id == external_id,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.raw_data = raw_data
                    existing.sync_status = "active"
                    existing.resource_name = resource_name
                else:
                    snap = ResourceSnapshot(
                        resource_type=resource_type,
                        external_id=external_id,
                        resource_name=resource_name,
                        sync_status="active",
                        raw_data=raw_data,
                    )
                    session.add(snap)
                await session.commit()

        asyncio.create_task(_do_upsert())

    def _build_vm_summary(self, vm: Any) -> VMSummary:
        detail = self.factory.get_vm_detail(vm)
        disks = [
            VMDisk(
                label=d.get("disk_file", "Unknown"),
                capacity_gb=d.get("capacity_gb", 0) or 0,
                thin_provisioned=d.get("thin_provisioned", True),
                datastore_name=d.get("datastore_name"),
            )
            for d in detail.get("disks", [])
        ]
        nics = [
            VMNic(
                label=n.get("label", "Unknown"),
                network_name=n.get("network_name", "unknown"),
                mac_address=n.get("mac_address"),
                ip_addresses=n.get("ip_addresses", []),
            )
            for n in detail.get("nics", [])
        ]
        hw = VMHardware(
            cpu_count=detail.get("cpu_count", 0),
            cpu_cores_per_socket=detail.get("cpu_cores_per_socket", 1),
            memory_mb=detail.get("memory_mb", 0),
            disks=disks,
            nics=nics,
        )
        return VMSummary(
            id=detail.get("id", ""),
            name=detail.get("name", ""),
            power_state=detail.get("power_state", "unknown"),
            guest_os=detail.get("guest_os", ""),
            hardware=hw,
            cluster_name=detail.get("cluster_name"),
            datastores=detail.get("datastores", []),
            tags=[],
            annotation=detail.get("annotation", ""),
        )

    @staticmethod
    def _build_datastore_summary(ds: Any) -> DatastoreSummary:
        detail = VMwareInventoryService._get_raw_ds_detail(ds)
        return DatastoreSummary(
            name=detail.get("name", ""),
            type=detail.get("type", ""),
            capacity_gb=detail.get("capacity_gb", 0.0),
            free_gb=detail.get("free_gb", 0.0),
            accessible=detail.get("accessible", True),
            maintenance_mode=detail.get("maintenance_mode", "normal"),
        )

    @staticmethod
    def _get_raw_ds_detail(ds: Any) -> dict[str, Any]:
        summary = getattr(ds, "summary", None)
        capacity = 0
        free = 0
        if summary:
            cap = getattr(summary, "capacity", None)
            if cap:
                capacity = cap
            f = getattr(summary, "freeSpace", None)
            if f:
                free = f
        return {
            "name": str(getattr(ds, "name", "")),
            "type": str(getattr(summary, "type", "")) if summary else "",
            "capacity_gb": round(capacity / (1024**3), 2) if capacity else 0.0,
            "free_gb": round(free / (1024**3), 2) if free else 0.0,
            "accessible": bool(getattr(summary, "accessible", True)) if summary else True,
            "maintenance_mode": str(getattr(ds, "overallStatus", "normal")),
        }

    @staticmethod
    def _build_network_summary(net: Any) -> NetworkSummary:
        detail = VMwareInventoryService._get_raw_net_detail(net)
        return NetworkSummary(
            name=detail.get("name", ""),
            type=detail.get("type", "network"),
            vlan_id=detail.get("vlan_id"),
            accessible=detail.get("accessible", True),
        )

    @staticmethod
    def _get_raw_net_detail(net: Any) -> dict[str, Any]:
        from pyVmomi import vim

        vlan_id = None
        if isinstance(net, vim.dvs.DistributedVirtualPortgroup):
            if hasattr(net, "config") and net.config:
                vlan_id = getattr(net.config, "vlanId", None)
        network_type = "network"
        if isinstance(net, vim.dvs.DistributedVirtualPortgroup):
            network_type = "distributed"
        elif isinstance(net, vim.OpaqueNetwork):
            network_type = "opaque"
        return {
            "name": str(getattr(net, "name", "")),
            "type": network_type,
            "vlan_id": vlan_id,
            "accessible": True,
        }
