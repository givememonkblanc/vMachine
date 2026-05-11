from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_vm_provisioning_engine
from app.schemas.openstack.vm_lifecycle import VMCreateRequest, VMDetail, VMOperationResponse
from app.services.openstack.vm_provisioning_engine import VMProvisioningEngine

router = APIRouter()


@router.post("/servers", response_model=VMDetail, status_code=status.HTTP_201_CREATED)
async def create_vm(
    payload: VMCreateRequest,
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> VMDetail:
    """Create a VM and wait for ACTIVE state."""
    return await engine.create_vm(payload)


@router.get("/servers", response_model=list[VMDetail])
async def list_vms(
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> list[VMDetail]:
    """List all VM instances."""
    return await engine.list_vms()


@router.get("/servers/{server_id}", response_model=VMDetail)
async def get_vm(
    server_id: str,
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> VMDetail:
    """Get a single VM detail."""
    return await engine.get_vm(server_id)


@router.post("/servers/{server_id}/start", response_model=VMOperationResponse)
async def start_vm(
    server_id: str,
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> VMOperationResponse:
    """Start (power on) a VM."""
    return await engine.start_vm(server_id)


@router.post("/servers/{server_id}/stop", response_model=VMOperationResponse)
async def stop_vm(
    server_id: str,
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> VMOperationResponse:
    """Stop (power off) a VM."""
    return await engine.stop_vm(server_id)


@router.post("/servers/{server_id}/reboot", response_model=VMOperationResponse)
async def reboot_vm(
    server_id: str,
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> VMOperationResponse:
    """Reboot a VM (soft reboot)."""
    return await engine.reboot_vm(server_id)


@router.delete("/servers/{server_id}", status_code=status.HTTP_200_OK)
async def delete_vm(
    server_id: str,
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> VMOperationResponse:
    """Delete (terminate) a VM instance."""
    return await engine.delete_vm(server_id)


@router.get("/servers/active/count")
async def active_vm_count(
    engine: Annotated[VMProvisioningEngine, Depends(get_vm_provisioning_engine)],
) -> dict[str, int]:
    """Return the current number of ACTIVE VM instances."""
    count = await engine.get_active_count()
    return {"active_count": count}
