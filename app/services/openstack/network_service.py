from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.common.utils.openstack_cache import cache_get, cache_invalidate, cache_set
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.network import (
    NetworkCreateRequest,
    NetworkSummary,
    SubnetSummary,
)


class NetworkService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        self._list_limit = get_settings().openstack_list_limit

    def list_networks(self) -> list[NetworkSummary]:
        cached = cache_get("networks")
        if cached is not None:
            return cached
        result = [
            NetworkSummary(
                **serialize_resource(
                    net, ["id", "name", "status", "shared", "admin_state_up"]
                )
            )
            for net in self.factory.call("network", "networks", limit=self._list_limit)
        ]
        cache_set("networks", result)
        return result

    def get_network(self, network_id: str) -> NetworkSummary:
        network = self.factory.call("network", "get_network", network_id)
        if not network:
            raise AppException(
                message="Network not found",
                status_code=404,
                error_code="network_not_found",
            )
        return NetworkSummary(
            **serialize_resource(
                network, ["id", "name", "status", "shared", "admin_state_up"]
            )
        )

    def get_network_subnets(self, network_id: str) -> list[SubnetSummary]:
        all_subnets = self.factory.call("network", "subnets")
        network_subnets = [
            subnet
            for subnet in all_subnets
            if getattr(subnet, "network_id", None) == network_id
        ]
        return [
            SubnetSummary(
                **serialize_resource(
                    subnet, ["id", "name", "cidr", "enable_dhcp", "gateway_ip"]
                )
            )
            for subnet in network_subnets
        ]

    def get_subnet(self, subnet_id: str) -> SubnetSummary:
        subnet = self.factory.call("network", "get_subnet", subnet_id)
        if not subnet:
            raise AppException(
                message="Subnet not found",
                status_code=404,
                error_code="subnet_not_found",
            )
        return SubnetSummary(
            **serialize_resource(
                subnet, ["id", "name", "cidr", "enable_dhcp", "gateway_ip"]
            )
        )

    def create_network(self, payload: NetworkCreateRequest) -> NetworkSummary:
        existing = self.factory.call(
            "network", "find_network", payload.name, ignore_missing=True
        )
        if existing:
            raise AppException(
                message=f"Network '{payload.name}' already exists",
                status_code=409,
                error_code="network_already_exists",
            )

        network = self.factory.call(
            "network",
            "create_network",
            name=payload.name,
            admin_state_up=True,
        )
        subnet = self.factory.call(
            "network",
            "create_subnet",
            name=f"{payload.name}-subnet",
            network_id=network.id,
            cidr=payload.cidr,
            ip_version=4,
            enable_dhcp=True,
        )
        _ = subnet
        cache_invalidate("networks")
        return NetworkSummary(
            **serialize_resource(
                network, ["id", "name", "status", "shared", "admin_state_up"]
            )
        )

    def delete_network(self, network_id: str) -> None:
        deleted = self.factory.call(
            "network", "delete_network", network_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Network not found",
                status_code=404,
                error_code="network_not_found",
            )
        cache_invalidate("networks")
