from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps.services import (
    get_operation_task_service,
    get_vmware_compatibility_service,
    get_vmware_inventory_service,
    get_vmware_mapping_engine,
    get_vmware_plan_service,
)
from app.schemas.vmware.assessment import (
    AssessmentResponse,
    AssessmentResult,
    MigrationPlanResponse,
    VMCompatibilityResult,
    VMMappingResult,
)
from app.services.core.operation_task_service import OperationTaskService
from app.services.vmware.compatibility import VMwareCompatibilityService
from app.services.vmware.inventory_service import VMwareInventoryService
from app.services.vmware.mapping_engine import VMwareMappingEngine
from app.services.vmware.plan_service import VMwarePlanService

router = APIRouter()


@router.post("/assess", response_model=AssessmentResponse, status_code=status.HTTP_200_OK)
async def assess_vms(
    vm_ids: list[str],
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
    compatibility_service: Annotated[VMwareCompatibilityService, Depends(get_vmware_compatibility_service)],
    mapping_engine: Annotated[VMwareMappingEngine, Depends(get_vmware_mapping_engine)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> AssessmentResponse:
    """VMware VM 목록에 대한 OpenStack 마이그레이션 적합성을 평가합니다."""
    from app.schemas.vmware.assessment import AssessmentRequest

    payload = AssessmentRequest(vm_ids=vm_ids)

    task = await operation_task_service.create_task(
        operation_type="vmware_assessment",
        target_type="assessment",
        target_id=",".join(payload.vm_ids[:5]),
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        assessments: list[AssessmentResult] = []
        for vm_id in payload.vm_ids:
            vm = inventory_service.get_vm(vm_id)
            if not vm:
                continue
            compatibility = compatibility_service.evaluate(vm)
            mapping = None
            if payload.include_mapping:
                mapping = mapping_engine.map_vm(vm)
            assessments.append(
                AssessmentResult(
                    vm_id=vm.id,
                    vm_name=vm.name,
                    compatibility=compatibility,
                    mapping=mapping,
                )
            )

        compatible = sum(1 for a in assessments if a.compatibility.compatible)
        total_warnings = sum(len(a.compatibility.warnings) for a in assessments)
        summary = {
            "total": len(assessments),
            "compatible": compatible,
            "incompatible": len(assessments) - compatible,
            "warning_count": total_warnings,
        }

        _ = await operation_task_service.update_task(task.id, state="succeeded")
        return AssessmentResponse(
            assessments=assessments,
            summary=summary,
            operation_task_id=task.id,
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise


@router.post("/assess/{vm_id}/compatibility", response_model=VMCompatibilityResult)
def assess_single_compatibility(
    vm_id: str,
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
    compatibility_service: Annotated[VMwareCompatibilityService, Depends(get_vmware_compatibility_service)],
) -> VMCompatibilityResult:
    """단일 VMware VM의 OpenStack 마이그레이션 호환성을 평가합니다."""
    vm = inventory_service.get_vm(vm_id)
    if not vm:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"VM '{vm_id}' not found")
    return compatibility_service.evaluate(vm)


@router.post("/assess/{vm_id}/mapping", response_model=VMMappingResult)
def map_single_vm(
    vm_id: str,
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
    mapping_engine: Annotated[VMwareMappingEngine, Depends(get_vmware_mapping_engine)],
) -> VMMappingResult:
    """단일 VMware VM에 대한 OpenStack 리소스 매핑 결과를 조회합니다."""
    vm = inventory_service.get_vm(vm_id)
    if not vm:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"VM '{vm_id}' not found")
    return mapping_engine.map_vm(vm)


@router.post("/plan", response_model=MigrationPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_migration_plan(
    vm_ids: list[str],
    inventory_service: Annotated[VMwareInventoryService, Depends(get_vmware_inventory_service)],
    compatibility_service: Annotated[VMwareCompatibilityService, Depends(get_vmware_compatibility_service)],
    mapping_engine: Annotated[VMwareMappingEngine, Depends(get_vmware_mapping_engine)],
    plan_service: Annotated[VMwarePlanService, Depends(get_vmware_plan_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> MigrationPlanResponse:
    """VMware VM 목록에 대한 마이그레이션 계획을 생성합니다."""
    from app.schemas.vmware.assessment import MigrationPlanRequest

    payload = MigrationPlanRequest(vm_ids=vm_ids)

    task = await operation_task_service.create_task(
        operation_type="vmware_migration_plan",
        target_type="plan",
        target_id=",".join(payload.vm_ids[:5]),
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        # Gather VM data
        vms = []
        for vm_id in payload.vm_ids:
            vm = inventory_service.get_vm(vm_id)
            if not vm:
                continue
            compatibility = compatibility_service.evaluate(vm)
            mapping = mapping_engine.map_vm(vm)
            vms.append((vm, compatibility, mapping))

        plan = plan_service.generate_plan(vms, payload.priority_overrides)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
        return plan.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise
