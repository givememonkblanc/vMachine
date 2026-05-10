from typing import Any

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.router import RouterCreateRequest, RouterCreateResponse, RouterSummary


class RouterService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def get_router(self, router_id: str) -> RouterSummary:
        conn = self.factory.create()
        try:
            router = conn.network.get_router(router_id)
            if not router:
                raise AppException(message="Router not found", status_code=404, error_code="router_not_found")
            return RouterSummary(
                **serialize_resource(router, ["id", "name", "status", "admin_state_up", "external_gateway_info"])
            )
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get router: {exc}") from exc

    def list_routers(self) -> list[RouterSummary]:
        conn = self.factory.create()
        try:
            return [
                RouterSummary(
                    **serialize_resource(router, ["id", "name", "status", "admin_state_up", "external_gateway_info"])
                )
                for router in conn.network.routers()
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list routers: {exc}") from exc

    def create_router(self, payload: RouterCreateRequest) -> RouterCreateResponse:
        conn = self.factory.create()
        try:
            existing_router = conn.network.find_router(payload.name, ignore_missing=True)
            if existing_router:
                raise AppException(
                    message="Router with the same name already exists",
                    status_code=409,
                    error_code="router_conflict",
                )

            kwargs: dict[str, Any] = {
                "name": payload.name,
                "admin_state_up": payload.admin_state_up,
            }
            if payload.external_network_id:
                kwargs["external_gateway_info"] = {"network_id": payload.external_network_id}

            router = conn.network.create_router(**kwargs)
            return RouterCreateResponse(router_id=router.id, name=payload.name)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create router: {exc}") from exc

    def delete_router(self, router_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.network.delete_router(router_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Router not found", status_code=404, error_code="router_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete router: {exc}") from exc

    def add_interface(self, router_id: str, subnet_id: str) -> None:
        conn = self.factory.create()
        try:
            router = conn.network.get_router(router_id)
            if not router:
                raise AppException(message="Router not found", status_code=404, error_code="router_not_found")
            
            conn.network.add_interface_to_router(router, subnet_id=subnet_id)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to add interface to router: {exc}") from exc

    def remove_interface(self, router_id: str, subnet_id: str) -> None:
        conn = self.factory.create()
        try:
            router = conn.network.get_router(router_id)
            if not router:
                raise AppException(message="Router not found", status_code=404, error_code="router_not_found")
            
            conn.network.remove_interface_from_router(router, subnet_id=subnet_id)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to remove interface from router: {exc}") from exc
