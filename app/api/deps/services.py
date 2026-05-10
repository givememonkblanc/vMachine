from app.clients.kubernetes.connection import KubernetesClientFactory
from app.clients.openstack.connection import OpenStackConnectionFactory
from app.core.config.settings import get_settings
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.cluster_service import ClusterService
from app.services.compute_service import ComputeService
from app.services.flavor_service import FlavorService
from app.services.image_service import ImageService
from app.services.keypair_service import KeypairService
from app.services.kubernetes_service import KubernetesService
from app.services.migration_service import MigrationService
from app.services.monitoring_service import MonitoringService
from app.services.network_service import NetworkService
from app.services.operations_service import OperationsService
from app.services.operation_task_service import OperationTaskService
from app.services.router_service import RouterService
from app.services.security_group_service import SecurityGroupService
from app.services.storage_service import StorageService
from app.services.tenant_service import TenantService
from app.services.volume_service import VolumeService


def get_openstack_factory() -> OpenStackConnectionFactory:
    return OpenStackConnectionFactory(get_settings())


def get_auth_service() -> AuthService:
    return AuthService(get_openstack_factory())


def get_audit_service() -> AuditService:
    return AuditService()


def get_compute_service() -> ComputeService:
    return ComputeService(get_openstack_factory())


def get_flavor_service() -> FlavorService:
    return FlavorService(get_openstack_factory())


def get_image_service() -> ImageService:
    return ImageService(get_openstack_factory())


def get_keypair_service() -> KeypairService:
    return KeypairService(get_openstack_factory())


def get_network_service() -> NetworkService:
    return NetworkService(get_openstack_factory())


def get_operation_task_service() -> OperationTaskService:
    return OperationTaskService()


def get_router_service() -> RouterService:
    return RouterService(get_openstack_factory())


def get_security_group_service() -> SecurityGroupService:
    return SecurityGroupService(get_openstack_factory())


def get_tenant_service() -> TenantService:
    return TenantService(get_openstack_factory())


def get_volume_service() -> VolumeService:
    return VolumeService(get_openstack_factory())


def get_kubernetes_factory() -> KubernetesClientFactory:
    return KubernetesClientFactory(get_settings())


def get_kubernetes_service() -> KubernetesService:
    return KubernetesService(get_kubernetes_factory())


def get_monitoring_service() -> MonitoringService:
    return MonitoringService()


def get_cluster_service() -> ClusterService:
    return ClusterService(compute_service=get_compute_service())


def get_migration_service() -> MigrationService:
    return MigrationService()


def get_operations_service() -> OperationsService:
    return OperationsService()


def get_storage_service() -> StorageService:
    return StorageService()
