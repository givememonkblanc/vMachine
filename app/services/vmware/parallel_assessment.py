import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.common.metrics.custom import (
    vmw_assessment_queue_depth,
    vmw_assessment_timeouts_total,
    vmw_assessment_retries_total,
)
from app.schemas.vmware.assessment import (
    ParallelAssessmentProgress,
    ScoredCompatibilityResult,
    VMMappingResult,
)
from app.schemas.vmware.inventory import VMSummary
from app.services.vmware.compatibility import VMwareCompatibilityService
from app.services.vmware.inventory_service import VMwareInventoryService
from app.services.vmware.mapping_engine import VMwareMappingEngine
from app.services.core.operation_task_service import OperationTaskService


@dataclass
class SingleVMResult:
    vm_id: str
    vm_name: str
    status: str
    compatibility_result: ScoredCompatibilityResult | None = None
    mapping_result: VMMappingResult | None = None
    error_message: str | None = None
    duration_ms: float = 0.0
    evaluated_at: str = ""


class ParallelAssessmentService:
    def __init__(
        self,
        inventory_service: VMwareInventoryService,
        compatibility_service: VMwareCompatibilityService,
        mapping_engine: VMwareMappingEngine,
        operation_task_service: OperationTaskService | None = None,
    ):
        self._inventory = inventory_service
        self._compatibility = compatibility_service
        self._mapping_engine = mapping_engine
        self._operation_task = operation_task_service
        self._tasks: dict[str, ParallelAssessmentProgress] = {}
        self._results: dict[str, list[SingleVMResult]] = {}

    @property
    def inventory_service(self) -> VMwareInventoryService:
        return self._inventory

    @property
    def compatibility_service(self) -> VMwareCompatibilityService:
        return self._compatibility

    @property
    def mapping_engine(self) -> VMwareMappingEngine:
        return self._mapping_engine

    async def assess_parallel(
        self,
        vm_ids: list[str],
        include_mapping: bool = True,
        max_concurrency: int = 10,
        timeout_seconds: int = 300,
    ) -> ParallelAssessmentProgress:
        task_id = str(uuid.uuid4())
        progress = ParallelAssessmentProgress(
            task_id=task_id,
            total_vms=len(vm_ids),
            completed=0,
            failed=0,
            in_progress=len(vm_ids),
            status="running",
        )
        self._tasks[task_id] = progress
        self._results[task_id] = []

        vmw_assessment_queue_depth.set(len(vm_ids))

        if self._operation_task:
            op_task = await self._operation_task.create_task(
                operation_type="vmware_parallel_assessment",
                target_type="assessment",
                target_id=",".join(vm_ids[:5]),
            )
            await self._operation_task.update_task(op_task.id, state="running")

        semaphore = asyncio.Semaphore(max_concurrency)

        async def _evaluate_one(vm_id: str) -> SingleVMResult:
            async with semaphore:
                start = time.perf_counter()
                try:
                    result = await asyncio.wait_for(
                        self._evaluate_single(vm_id, include_mapping),
                        timeout=timeout_seconds,
                    )
                    result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    return result
                except asyncio.TimeoutError:
                    vmw_assessment_timeouts_total.inc()
                    return SingleVMResult(
                        vm_id=vm_id,
                        vm_name="",
                        status="timeout",
                        error_message=f"Evaluation timed out after {timeout_seconds}s",
                        duration_ms=timeout_seconds * 1000,
                    )
                except Exception as exc:
                    vmw_assessment_retries_total.labels(operation="evaluate_single").inc()
                    try:
                        retry_start = time.perf_counter()
                        retry_result = await asyncio.wait_for(
                            self._evaluate_single(vm_id, include_mapping),
                            timeout=timeout_seconds,
                        )
                        retry_result.duration_ms = round((time.perf_counter() - retry_start) * 1000, 2)
                        return retry_result
                    except asyncio.TimeoutError:
                        vmw_assessment_timeouts_total.inc()
                        return SingleVMResult(
                            vm_id=vm_id,
                            vm_name="",
                            status="timeout",
                            error_message=f"Evaluation timed out after {timeout_seconds}s (retry)",
                            duration_ms=timeout_seconds * 1000,
                        )
                    except Exception:
                        return SingleVMResult(
                            vm_id=vm_id,
                            vm_name="",
                            status="failed",
                            error_message=str(exc),
                            duration_ms=round((time.perf_counter() - start) * 1000, 2),
                        )

        coros = [_evaluate_one(vm_id) for vm_id in vm_ids]
        results: list[SingleVMResult] = []
        completed = 0
        failed = 0

        try:
            for coro in asyncio.as_completed(coros):
                single = await coro
                results.append(single)
                if single.status == "completed":
                    completed += 1
                else:
                    failed += 1
                remaining = len(vm_ids) - completed - failed
                self._tasks[task_id].completed = completed
                self._tasks[task_id].failed = failed
                self._tasks[task_id].in_progress = remaining
                vmw_assessment_queue_depth.set(remaining)

            final_status = "completed" if failed == 0 else "completed_with_errors"
            self._tasks[task_id].status = final_status
            self._tasks[task_id].completed = completed
            self._tasks[task_id].failed = failed
            self._tasks[task_id].in_progress = 0
            self._results[task_id] = results

            if self._operation_task:
                await self._operation_task.update_task(
                    op_task.id,
                    state="succeeded" if final_status == "completed" else "failed",
                )
        finally:
            vmw_assessment_queue_depth.set(0)

        return self._tasks[task_id]

    async def _evaluate_single(
        self, vm_id: str, include_mapping: bool
    ) -> SingleVMResult:
        vm: VMSummary | None = self._inventory.get_vm(vm_id)
        if not vm:
            return SingleVMResult(
                vm_id=vm_id,
                vm_name="",
                status="failed",
                error_message=f"VM '{vm_id}' not found in inventory",
            )

        compatibility: ScoredCompatibilityResult = self._compatibility.evaluate(vm)
        mapping: VMMappingResult | None = None
        if include_mapping:
            mapping = self._mapping_engine.map_vm(vm)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return SingleVMResult(
            vm_id=vm.id,
            vm_name=vm.name,
            status="completed",
            compatibility_result=compatibility,
            mapping_result=mapping,
            evaluated_at=now,
        )

    def get_progress(self, task_id: str) -> ParallelAssessmentProgress | None:
        return self._tasks.get(task_id)

    def get_results(self, task_id: str) -> list[SingleVMResult] | None:
        return self._results.get(task_id)


__all__ = ["ParallelAssessmentService", "SingleVMResult"]
