from fastapi import APIRouter

from app.api.v1.endpoints.core import audit, health
from app.api.v1.endpoints.identity import auth, tenants
from app.api.v1.endpoints.openstack import compute, flavors, images, keypairs, networks, routers, security_groups, storage, volumes
from app.api.v1.endpoints.orchestration import clusters, migrations, operations
from app.api.v1.endpoints.kubernetes import kubernetes
from app.api.v1.endpoints.monitoring import monitoring
from app.api.v1.endpoints.vmware import inventory as vmware_inventory, assessment as vmware_assessment

api_router = APIRouter()

# Core
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(health.router, tags=["health"])

# Identity
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])

# OpenStack infra
api_router.include_router(compute.router, prefix="/compute", tags=["compute"])
api_router.include_router(flavors.router, prefix="/flavors", tags=["flavors"])
api_router.include_router(images.router, prefix="/images", tags=["images"])
api_router.include_router(keypairs.router, prefix="/keypairs", tags=["keypairs"])
api_router.include_router(networks.router, prefix="/networks", tags=["networks"])
api_router.include_router(routers.router, prefix="/routers", tags=["routers"])
api_router.include_router(security_groups.router, prefix="/security-groups", tags=["security_groups"])
api_router.include_router(storage.router, prefix="/storage", tags=["storage"])
api_router.include_router(volumes.router, prefix="/volumes", tags=["volumes"])

# Orchestration
api_router.include_router(clusters.router, prefix="/clusters", tags=["clusters"])
api_router.include_router(migrations.router, prefix="/migrations", tags=["migrations"])
api_router.include_router(operations.router, prefix="/operations", tags=["operations"])

# Kubernetes
api_router.include_router(kubernetes.router, prefix="/k8s", tags=["kubernetes"])

# Monitoring
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])

# VMware
api_router.include_router(vmware_inventory.router, prefix="/vmware", tags=["vmware"])
api_router.include_router(vmware_assessment.router, prefix="/vmware", tags=["vmware"])
