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

    def export_vm_disk(self, vm: Any, export_path: str) -> str:
        return f"{export_path}/{vm.name}.vmdk"
