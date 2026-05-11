from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps.services import (
    get_assessment_persistence_service,
    get_operation_task_service,
    get_parallel_assessment_service,
    get_vmware_compatibility_service,
    get_vmware_inventory_service,
    get_vmware_mapping_engine,
    get_vmware_plan_service,
)
from app.schemas.vmware.assessment import (
    AssessmentResponse,
    AssessmentResult,
    MigrationPlanResponse,
    ParallelAssessmentProgress,
    PersistedAssessmentDetail,
    PersistedAssessmentSummary,
    PersistedPlanDetail,
    PersistedPlanSummary,
    ScoredCompatibilityResult,
    VMMappingResult,
)
from app.services.core.operation_task_service import OperationTaskService
from app.services.vmware.assessment_persistence import AssessmentPersistenceService
from app.services.vmware.compatibility import VMwareCompatibilityService
from app.services.vmware.inventory_service import VMwareInventoryService
from app.services.vmware.mapping_engine import VMwareMappingEngine
from app.services.vmware.parallel_assessment import ParallelAssessmentService
from app.services.vmware.plan_service import VMwarePlanService

router = APIRouter()


@router.post(
    "/assess", response_model=AssessmentResponse, status_code=status.HTTP_200_OK
)
async def assess_vms(
    vm_ids: list[str],
    inventory_service: Annotated[
        VMwareInventoryService, Depends(get_vmware_inventory_service)
    ],
    compatibility_service: Annotated[
        VMwareCompatibilityService, Depends(get_vmware_compatibility_service)
    ],
    mapping_engine: Annotated[VMwareMappingEngine, Depends(get_vmware_mapping_engine)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> AssessmentResponse:
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
        total_issues = sum(len(a.compatibility.issues) for a in assessments)
        summary = {
            "total": len(assessments),
            "compatible": compatible,
            "incompatible": len(assessments) - compatible,
            "warning_count": total_issues,
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


@router.post("/assess/{vm_id}/compatibility", response_model=ScoredCompatibilityResult)
def assess_single_compatibility(
    vm_id: str,
    inventory_service: Annotated[
        VMwareInventoryService, Depends(get_vmware_inventory_service)
    ],
    compatibility_service: Annotated[
        VMwareCompatibilityService, Depends(get_vmware_compatibility_service)
    ],
) -> ScoredCompatibilityResult:
    vm = inventory_service.get_vm(vm_id)
    if not vm:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"VM '{vm_id}' not found")
    return compatibility_service.evaluate(vm)


@router.post("/assess/{vm_id}/mapping", response_model=VMMappingResult)
def map_single_vm(
    vm_id: str,
    inventory_service: Annotated[
        VMwareInventoryService, Depends(get_vmware_inventory_service)
    ],
    mapping_engine: Annotated[VMwareMappingEngine, Depends(get_vmware_mapping_engine)],
) -> VMMappingResult:
    vm = inventory_service.get_vm(vm_id)
    if not vm:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"VM '{vm_id}' not found")
    return mapping_engine.map_vm(vm)


@router.post(
    "/plan", response_model=MigrationPlanResponse, status_code=status.HTTP_201_CREATED
)
async def create_migration_plan(
    vm_ids: list[str],
    inventory_service: Annotated[
        VMwareInventoryService, Depends(get_vmware_inventory_service)
    ],
    compatibility_service: Annotated[
        VMwareCompatibilityService, Depends(get_vmware_compatibility_service)
    ],
    mapping_engine: Annotated[VMwareMappingEngine, Depends(get_vmware_mapping_engine)],
    plan_service: Annotated[VMwarePlanService, Depends(get_vmware_plan_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> MigrationPlanResponse:
    from app.schemas.vmware.assessment import MigrationPlanRequest

    payload = MigrationPlanRequest(vm_ids=vm_ids)

    task = await operation_task_service.create_task(
        operation_type="vmware_migration_plan",
        target_type="plan",
        target_id=",".join(payload.vm_ids[:5]),
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
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


@router.get("/assessments", response_model=list[PersistedAssessmentSummary])
async def list_persisted_assessments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    compatible_only: bool | None = None,
    persistence: Annotated[
        AssessmentPersistenceService, Depends(get_assessment_persistence_service)
    ] = None,  # type: ignore[assignment]
) -> list[PersistedAssessmentSummary]:
    return await persistence.list_assessments(
        limit=limit, offset=offset, compatible_only=compatible_only
    )


@router.get("/assessment/{assessment_id}", response_model=PersistedAssessmentDetail)
async def get_persisted_assessment(
    assessment_id: str,
    persistence: Annotated[
        AssessmentPersistenceService, Depends(get_assessment_persistence_service)
    ] = None,  # type: ignore[assignment]
) -> PersistedAssessmentDetail:
    result = await persistence.get_assessment(assessment_id)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"Assessment '{assessment_id}' not found"
        )
    return result


@router.get("/plans", response_model=list[PersistedPlanSummary])
async def list_persisted_plans(
    assessment_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    persistence: Annotated[
        AssessmentPersistenceService, Depends(get_assessment_persistence_service)
    ] = None,  # type: ignore[assignment]
) -> list[PersistedPlanSummary]:
    return await persistence.list_plans(
        assessment_id=assessment_id, limit=limit, offset=offset
    )


@router.get("/plan/{plan_id}", response_model=PersistedPlanDetail)
async def get_persisted_plan(
    plan_id: str,
    persistence: Annotated[
        AssessmentPersistenceService, Depends(get_assessment_persistence_service)
    ] = None,  # type: ignore[assignment]
) -> PersistedPlanDetail:
    result = await persistence.get_plan(plan_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
    return result


@router.post("/assess/parallel", response_model=ParallelAssessmentProgress)
async def assess_vms_parallel(
    vm_ids: list[str],
    include_mapping: bool = Query(default=True),
    max_concurrency: int = Query(default=10, ge=1, le=50),
    timeout_seconds: int = Query(default=300, ge=10, le=3600),
    parallel_service: Annotated[
        ParallelAssessmentService, Depends(get_parallel_assessment_service)
    ] = None,  # type: ignore[assignment]
) -> ParallelAssessmentProgress:
    return await parallel_service.assess_parallel(
        vm_ids=vm_ids,
        include_mapping=include_mapping,
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
    )


@router.get("/assess/parallel/{task_id}", response_model=ParallelAssessmentProgress)
async def get_parallel_progress(
    task_id: str,
    parallel_service: Annotated[
        ParallelAssessmentService, Depends(get_parallel_assessment_service)
    ] = None,  # type: ignore[assignment]
) -> ParallelAssessmentProgress:
    progress = parallel_service.get_progress(task_id)
    if not progress:
        raise HTTPException(
            status_code=404, detail=f"Parallel task '{task_id}' not found"
        )
    return progress
