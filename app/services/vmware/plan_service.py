import uuid
from datetime import datetime, timezone

from app.schemas.vmware.assessment import (
    MigrationPlanResponse,
    MigrationPlanVM,
    MigrationStep,
    ScoredCompatibilityResult,
    VMMappingResult,
)
from app.schemas.vmware.inventory import VMSummary


class VMwarePlanService:
    """VMware VM 마이그레이션 계획을 생성합니다.

    계획 수립 로직
    --------------
    - 호환 가능한 VM만 계획에 포함
    - 전원이 켜진 VM 우선 (downtime 예측 용이)
    - Flavor/Network/Disk 매핑 결과를 실행 단계로 변환
    """

    def generate_plan(
        self,
        vms: list[tuple[VMSummary, ScoredCompatibilityResult, VMMappingResult | None]],
        priority_overrides: dict[str, int] | None = None,
    ) -> MigrationPlanResponse:
        overrides = priority_overrides or {}
        plan_vms: list[MigrationPlanVM] = []

        for vm, compatibility, mapping in vms:
            if not compatibility.compatible:
                continue

            priority = overrides.get(vm.id, 5)
            target_flavor_id = mapping.flavor_match.flavor_id if mapping and mapping.flavor_match else None
            target_network_ids = [
                nm.openstack_network_id
                for nm in (mapping.network_mappings if mapping else [])
                if nm.openstack_network_id
            ]
            target_volume_types = [
                dm.openstack_volume_type
                for dm in (mapping.disk_mappings if mapping else [])
                if dm.openstack_volume_type
            ]

            steps = self._build_steps(vm, mapping)
            estimated_total = sum(s.estimated_minutes for s in steps)
            downtime = self._estimate_downtime(vm)

            plan_vms.append(
                MigrationPlanVM(
                    vm_id=vm.id,
                    vm_name=vm.name,
                    priority=priority,
                    target_flavor_id=target_flavor_id,
                    target_network_ids=target_network_ids,
                    target_volume_types=target_volume_types,
                    estimated_downtime_minutes=downtime,
                    steps=steps,
                    estimated_total_minutes=estimated_total,
                )
            )

        plan_vms.sort(key=lambda pvm: (pvm.priority, pvm.vm_name))

        total_minutes = sum(pvm.estimated_total_minutes for pvm in plan_vms)

        return MigrationPlanResponse(
            plan_id=str(uuid.uuid4()),
            vms=plan_vms,
            total_vms=len(plan_vms),
            total_estimated_minutes=total_minutes,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _build_steps(vm: VMSummary, mapping: VMMappingResult | None) -> list[MigrationStep]:
        steps: list[MigrationStep] = []
        order = 1

        if mapping and mapping.flavor_match:
            steps.append(
                MigrationStep(
                    order=order,
                    action="verify_flavor",
                    description=f"Verify target flavor '{mapping.flavor_match.flavor_name}' exists in OpenStack",
                    resource_id=mapping.flavor_match.flavor_id,
                    estimated_minutes=1,
                )
            )
            order += 1

        if mapping:
            for nm in mapping.network_mappings:
                if nm.match_type != "not_found":
                    steps.append(
                        MigrationStep(
                            order=order,
                            action="verify_network",
                            description=f"Map VMware network '{nm.vm_network}' to OpenStack network '{nm.openstack_network_name or '?'}'",
                            resource_id=nm.openstack_network_id,
                            estimated_minutes=1,
                        )
                    )
                    order += 1
                else:
                    steps.append(
                        MigrationStep(
                            order=order,
                            action="create_network",
                            description=f"Create OpenStack network for VMware port group '{nm.vm_network}'",
                            estimated_minutes=3,
                        )
                    )
                    order += 1

        if mapping:
            for dm in mapping.disk_mappings:
                steps.append(
                    MigrationStep(
                        order=order,
                        action="create_volume",
                        description=f"Create {dm.openstack_size_gb} GB volume for '{dm.vm_disk_label}'",
                        estimated_minutes=2 if dm.bootable else 1,
                    )
                )
                order += 1

        steps.append(
            MigrationStep(
                order=order,
                action="import_image",
                description=f"Export VM '{vm.name}' disk and upload to OpenStack Glance",
                estimated_minutes=15,
            )
        )
        order += 1

        steps.append(
            MigrationStep(
                order=order,
                action="create_server",
                description=f"Create OpenStack server from imported image with matched flavor and networks",
                estimated_minutes=5,
            )
        )
        order += 1

        steps.append(
            MigrationStep(
                order=order,
                action="cleanup",
                description="Clean up temporary exported disk files",
                estimated_minutes=1,
            )
        )

        return steps

    @staticmethod
    def _estimate_downtime(vm: VMSummary) -> int:
        power = vm.power_state.lower()
        if power == "poweredoff":
            return 0
        if power == "suspended":
            return 5
        total_disk = sum(d.capacity_gb for d in (vm.hardware.disks if vm.hardware else [])) if vm.hardware else 0
        if total_disk > 500:
            return 30
        if total_disk > 100:
            return 15
        return 10
