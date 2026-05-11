from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.schemas.openstack.router import RouterCreateRequest, RouterSummary


class RouterService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def get_router(self, router_id: str) -> RouterSummary:
        router = self.factory.call("network", "get_router", router_id)
        if not router:
            raise AppException(
                message="Router not found",
                status_code=404,
                error_code="router_not_found",
            )
        return RouterSummary(
            id=router.id,
            name=getattr(router, "name", ""),
            status=getattr(router, "status", ""),
            admin_state_up=getattr(router, "admin_state_up", True),
        )

    def list_routers(self) -> list[RouterSummary]:
        return [
            RouterSummary(
                id=r.id,
                name=getattr(r, "name", ""),
                status=getattr(r, "status", ""),
                admin_state_up=getattr(r, "admin_state_up", True),
            )
            for r in self.factory.call("network", "routers")
        ]

    def create_router(self, payload: RouterCreateRequest) -> RouterSummary:
        existing = self.factory.call(
            "network", "find_router", payload.name, ignore_missing=True
        )
        if existing:
            raise AppException(
                message=f"Router '{payload.name}' already exists",
                status_code=409,
                error_code="router_already_exists",
            )
        router = self.factory.call(
            "network", "create_router", name=payload.name, admin_state_up=True
        )
        return RouterSummary(
            id=router.id,
            name=getattr(router, "name", ""),
            status=getattr(router, "status", ""),
            admin_state_up=getattr(router, "admin_state_up", True),
        )

    def delete_router(self, router_id: str) -> None:
        deleted = self.factory.call(
            "network", "delete_router", router_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Router not found",
                status_code=404,
                error_code="router_not_found",
            )

    def attach_subnet(self, router_id: str, subnet_id: str) -> None:
        router = self.factory.call("network", "get_router", router_id)
        if not router:
            raise AppException(
                message="Router not found",
                status_code=404,
                error_code="router_not_found",
            )
        self.factory.call(
            "network", "add_interface_to_router", router, subnet_id=subnet_id
        )

    def detach_subnet(self, router_id: str, subnet_id: str) -> None:
        router = self.factory.call("network", "get_router", router_id)
        if not router:
            raise AppException(
                message="Router not found",
                status_code=404,
                error_code="router_not_found",
            )
        self.factory.call(
            "network", "remove_interface_from_router", router, subnet_id=subnet_id
        )
