import uuid

from sqlalchemy import select

from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.cluster_deployment import ClusterDeployment
from app.schemas.orchestration.deployment import (
    BatchDeployRequest,
    BatchDeployResponse,
    ClusterCreateRequest,
    ClusterListResponse,
    ClusterSummary,
)
from app.services.openstack.compute_service import ComputeService


class ClusterService:
    def __init__(self, compute_service: ComputeService | None = None) -> None:
        self._compute = compute_service

    async def list_clusters(self) -> ClusterListResponse:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ClusterDeployment).order_by(ClusterDeployment.created_at.desc())
            )
            clusters = result.scalars().all()
        return ClusterListResponse(items=[self._serialize(c) for c in clusters])

    async def get_cluster(self, cluster_id: str) -> ClusterSummary:
        async with SessionLocal() as session:
            cluster = await session.get(ClusterDeployment, uuid.UUID(cluster_id))
            if not cluster:
                raise AppException(message="Cluster not found", status_code=404, error_code="cluster_not_found")
            return self._serialize(cluster)

    async def create_cluster(self, payload: ClusterCreateRequest) -> ClusterSummary:
        async with SessionLocal() as session:
            existing = await session.execute(
                select(ClusterDeployment).where(ClusterDeployment.name == payload.name)
            )
            if existing.scalar_one_or_none():
                raise AppException(
                    message=f"Cluster '{payload.name}' already exists",
                    status_code=409,
                    error_code="cluster_already_exists",
                )

            cluster = ClusterDeployment(
                name=payload.name,
                description=payload.description,
                cluster_type=payload.cluster_type,
                node_count=payload.node_count,
                extra_config=payload.metadata,
                status="active",
            )
            session.add(cluster)
            await session.commit()
            await session.refresh(cluster)
            return self._serialize(cluster)

    async def delete_cluster(self, cluster_id: str) -> None:
        async with SessionLocal() as session:
            cluster = await session.get(ClusterDeployment, uuid.UUID(cluster_id))
            if not cluster:
                raise AppException(message="Cluster not found", status_code=404, error_code="cluster_not_found")
            await session.delete(cluster)
            await session.commit()

    async def batch_deploy(
        self, cluster_id: str, payload: BatchDeployRequest
    ) -> BatchDeployResponse:
        async with SessionLocal() as session:
            cluster = await session.get(ClusterDeployment, uuid.UUID(cluster_id))
            if not cluster:
                raise AppException(message="Cluster not found", status_code=404, error_code="cluster_not_found")

        created = 0
        for i in range(payload.instance_count):
            try:
                server_name = f"{payload.template_name}-{i + 1}"
                if self._compute:
                    self._compute.create_server(
                        type("Req", (), {
                            "name": server_name,
                            "image_id": payload.image_id,
                            "flavor_id": payload.flavor_id,
                            "network_id": payload.network_id,
                            "key_name": payload.key_name,
                            "availability_zone": payload.availability_zone,
                            "metadata": {"cluster_id": cluster_id, "template": payload.template_name},
                            "wait": False,
                        })()
                    )
                    created += 1
            except Exception:
                break

        return BatchDeployResponse(
            template_name=payload.template_name,
            requested=payload.instance_count,
            created=created,
        )

    @staticmethod
    def _serialize(cluster: ClusterDeployment) -> ClusterSummary:
        return ClusterSummary(
            id=str(cluster.id),
            name=cluster.name,
            description=cluster.description,
            cluster_type=cluster.cluster_type,
            status=cluster.status,
            node_count=cluster.node_count,
            created_at=cluster.created_at.isoformat() if cluster.created_at else None,
        )
