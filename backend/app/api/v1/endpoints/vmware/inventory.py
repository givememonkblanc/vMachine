from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps.services import (
    get_operation_task_service,
    get_vmware_inventory_service,
)
from app.schemas.vmware.inventory import (
    DatastoreListResponse,
    InventorySyncResponse,
    NetworkListResponse,
    VMListResponse,
    VMSummary,
)
from app.services.vmware.inventory_service import VMwareInventoryService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("/vms", response_model=VMListResponse)
def list_vms(
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
) -> VMListResponse:
    """VMware vCenter에서 관리 중인 가상 머신(VM) 목록을 조회합니다."""
    return inventory_service.list_vms(use_cache=True)


@router.get("/vms/{vm_id}", response_model=VMSummary)
def get_vm(
    vm_id: str,
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
) -> VMSummary:
    """특정 VMware VM의 상세 정보를 조회합니다."""
    vm = inventory_service.get_vm(vm_id)
    if not vm:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"VM '{vm_id}' not found")
    return vm


@router.get("/datastores", response_model=DatastoreListResponse)
def list_datastores(
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
) -> DatastoreListResponse:
    """VMware 데이터스토어 목록을 조회합니다."""
    return inventory_service.list_datastores(use_cache=True)


@router.get("/networks", response_model=NetworkListResponse)
def list_networks(
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
) -> NetworkListResponse:
    """VMware 네트워크/포트 그룹 목록을 조회합니다."""
    return inventory_service.list_networks(use_cache=True)


@router.post("/sync", response_model=InventorySyncResponse, status_code=status.HTTP_201_CREATED)
async def sync_inventory(
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> InventorySyncResponse:
    """VMware vCenter 인벤토리를 강제 동기화하고 스냅샷을 저장합니다."""
    task = await operation_task_service.create_task(
        operation_type="vmware_inventory_sync",
        target_type="inventory",
        target_id="vmware",
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        result = inventory_service.sync_inventory(operation_task_id=task.id)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
        return result
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise
