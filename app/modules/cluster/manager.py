from app.schemas.orchestration.deployment import (
    BatchDeployRequest,
    ClusterCreateRequest,
)
from app.services.openstack.compute_service import ComputeService
from app.services.orchestration.cluster_service import ClusterService


class ClusterManager:
    """클러스터 배포 및 관리 오케스트레이션"""

    def __init__(
        self,
        cluster_service: ClusterService | None = None,
        compute_service: ComputeService | None = None,
    ) -> None:
        self._cluster = cluster_service
        self._compute = compute_service

    async def provision_cluster_with_instances(
        self,
        name: str,
        instance_count: int,
        image_id: str,
        flavor_id: str,
        network_id: str,
    ) -> dict:
        """클러스터를 생성하고 지정된 수만큼 인스턴스를 배포합니다."""
        if not self._cluster:
            return {"error": "Cluster service not available"}

        cluster = await self._cluster.create_cluster(
            ClusterCreateRequest(
                name=name, cluster_type="compute", node_count=instance_count
            )
        )

        deploy_result = await self._cluster.batch_deploy(
            cluster.id,
            BatchDeployRequest(
                template_name=name,
                instance_count=instance_count,
                image_id=image_id,
                flavor_id=flavor_id,
                network_id=network_id,
            ),
        )

        return {
            "cluster_id": cluster.id,
            "deploy_result": deploy_result.model_dump(),
            "message": f"Cluster '{name}' with {deploy_result.created} instances provisioned",
        }
