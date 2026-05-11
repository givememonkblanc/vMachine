import ssl
from typing import Any

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

from app.common.exceptions.base import AppException
from app.core.config.settings import Settings


class VMwareClientException(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=500, error_code="vmware_integration_error")


class VMwareClientFactory:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.si = None

    def connect(self) -> Any:
        if not self.settings.vmware_ready:
            raise VMwareClientException("VMware settings are incomplete.")

        if self.si is not None:
            return self.si

        try:
            if self.settings.vmware_no_verify_ssl:
                context = ssl._create_unverified_context()
                self.si = SmartConnect(
                    host=self.settings.vmware_host,
                    user=self.settings.vmware_user,
                    pwd=self.settings.vmware_password,
                    sslContext=context,
                )
            else:
                self.si = SmartConnect(
                    host=self.settings.vmware_host,
                    user=self.settings.vmware_user,
                    pwd=self.settings.vmware_password,
                )
            return self.si
        except Exception as exc:
            raise VMwareClientException(f"Failed to connect to VMware: {exc}") from exc

    def disconnect(self) -> None:
        if self.si is not None:
            Disconnect(self.si)
            self.si = None

    def get_vm_by_name(self, vm_name: str) -> Any:
        si = self.connect()
        container = si.content.viewManager.CreateContainerView(si.content.rootFolder, [vim.VirtualMachine], True)

        for vm in container.view:
            if vm.name == vm_name:
                return vm

        raise VMwareClientException(f"VM '{vm_name}' not found in VMware")

    # ------------------------------------------------------------------
    # Inventory discovery helpers
    # ------------------------------------------------------------------

    def _get_all_objects(self, vim_type: type) -> list[Any]:
        si = self.connect()
        container = si.content.viewManager.CreateContainerView(
            si.content.rootFolder, [vim_type], True
        )
        return list(container.view)

    def list_vms(self) -> list[Any]:
        return self._get_all_objects(vim.VirtualMachine)

    def list_datastores(self) -> list[Any]:
        return self._get_all_objects(vim.Datastore)

    def list_networks(self) -> list[Any]:
        return self._get_all_objects(vim.Network)

    def list_clusters(self) -> list[Any]:
        return self._get_all_objects(vim.ClusterComputeResource)

    def list_hosts(self) -> list[Any]:
        return self._get_all_objects(vim.HostSystem)

    # ------------------------------------------------------------------
    # VM detail extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_vm_disks(vm: Any) -> list[dict[str, Any]]:
        disks: list[dict[str, Any]] = []
        if not hasattr(vm, "layout") or not vm.layout:
            return disks
        if not hasattr(vm.layout, "disk") or not vm.layout.disk:
            return disks
        for disk_layout in vm.layout.disk:
            if not hasattr(disk_layout, "diskFile") or not disk_layout.diskFile:
                continue
            for df in disk_layout.diskFile:
                disks.append({"disk_file": str(df), "capacity_gb": 0, "thin_provisioned": True})
        # Try to get precise disk info from guest hardware
        if hasattr(vm, "config") and vm.config and hasattr(vm.config, "hardware") and vm.config.hardware:
            hw = vm.config.hardware
            if hasattr(hw, "device"):
                for dev in hw.device:
                    if isinstance(dev, vim.vm.device.VirtualDisk):
                        backing = getattr(dev, "backing", None)
                        ds_name = None
                        if backing and hasattr(backing, "fileName") and backing.fileName:
                            parts = str(backing.fileName).strip("[]").split("] ")
                            ds_name = parts[0] if len(parts) > 0 else None
                        thin = False
                        if backing and hasattr(backing, "thinProvisioned"):
                            thin = bool(backing.thinProvisioned)
                        disks.append({
                            "disk_file": getattr(dev, "deviceInfo", None) and getattr(dev.deviceInfo, "label", None) or f"Hard disk {len(disks) + 1}",
                            "capacity_gb": dev.capacityInKB // (1024 * 1024) if hasattr(dev, "capacityInKB") and dev.capacityInKB else (dev.capacityInBytes // (1024**3) if hasattr(dev, "capacityInBytes") and dev.capacityInBytes else 0),
                            "thin_provisioned": thin,
                            "datastore_name": ds_name,
                        })
        return disks

    @staticmethod
    def _extract_vm_nics(vm: Any) -> list[dict[str, Any]]:
        nics: list[dict[str, Any]] = []
        if not hasattr(vm, "config") or not vm.config or not hasattr(vm.config, "hardware") or not vm.config.hardware:
            return nics
        for dev in vm.config.hardware.device:
            if isinstance(dev, vim.vm.device.VirtualEthernetCard):
                network_name = None
                if hasattr(dev, "backing") and dev.backing:
                    backing = dev.backing
                    if hasattr(backing, "deviceName") and backing.deviceName:
                        network_name = backing.deviceName
                    elif hasattr(backing, "port") and backing.port:
                        port = backing.port
                        if hasattr(port, "portgroupKey") and port.portgroupKey:
                            network_name = f"dvportgroup-{port.portgroupKey}"
                label = getattr(dev, "deviceInfo", None) and getattr(dev.deviceInfo, "label", None) or f"NIC {len(nics) + 1}"
                mac = getattr(dev, "macAddress", None)
                nics.append({
                    "label": label,
                    "network_name": network_name or "unknown",
                    "mac_address": mac,
                })
        return nics

    @staticmethod
    def _extract_vm_datastores(vm: Any) -> list[str]:
        ds_names: list[str] = []
        if not hasattr(vm, "datastore") or not vm.datastore:
            return ds_names
        for ds_ref in vm.datastore:
            if hasattr(ds_ref, "name") and ds_ref.name:
                ds_names.append(ds_ref.name)
        return ds_names

    def get_vm_detail(self, vm: Any) -> dict[str, Any]:
        config = getattr(vm, "config", None)
        hw = getattr(config, "hardware", None) if config else None
        guest = getattr(vm, "guest", None)
        summary = getattr(vm, "summary", None)
        guest_fullname = None
        if guest and hasattr(guest, "guestFullName"):
            guest_fullname = guest.guestFullName
        elif summary and hasattr(summary.config, "guestFullName"):
            guest_fullname = summary.config.guestFullName

        ip_addresses: list[str] = []
        if guest and hasattr(guest, "net"):
            for net in guest.net:
                if hasattr(net, "ipAddress") and net.ipAddress:
                    ip_addresses.extend(net.ipAddress)

        cluster_name = None
        parent = getattr(vm, "parent", None)
        if parent:
            if hasattr(parent, "name"):
                cluster_name = parent.name

        return {
            "id": str(getattr(vm, "moId", "") or getattr(summary, "moId", "")),
            "name": str(getattr(vm, "name", "")),
            "power_state": str(getattr(summary.runtime, "powerState", "unknown")) if summary and hasattr(summary, "runtime") else "unknown",
            "guest_os": guest_fullname or "",
            "cpu_count": getattr(hw, "numCPU", 0) if hw else 0,
            "cpu_cores_per_socket": getattr(hw, "numCoresPerSocket", 1) if hw else 1,
            "memory_mb": getattr(hw, "memoryMB", 0) if hw else 0,
            "disks": self._extract_vm_disks(vm),
            "nics": self._extract_vm_nics(vm),
            "datastores": self._extract_vm_datastores(vm),
            "cluster_name": cluster_name,
            "ip_addresses": ip_addresses,
            "annotation": str(config.annotation) if config and hasattr(config, "annotation") and config.annotation else "",
        }

    def get_datastore_detail(self, ds: Any) -> dict[str, Any]:
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

    def get_network_detail(self, net: Any) -> dict[str, Any]:
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

    def validate_credentials(self) -> bool:
        try:
            si = self.connect()
            return si is not None
        except Exception:
            return False

    def export_vm_disk(self, vm: Any, export_path: str) -> str:
        return f"{export_path}/{vm.name}.vmdk"
