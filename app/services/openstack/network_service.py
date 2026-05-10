from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.network import NetworkCreateRequest, NetworkCreateResponse, NetworkDetail, NetworkSummary, SubnetSummary


class NetworkService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_networks(self) -> list[NetworkSummary]:
        conn = self.factory.create()
        try:
            return [self._serialize_network_summary(network) for network in conn.network.networks()]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list networks: {exc}") from exc

    def get_network(self, network_id: str) -> NetworkDetail:
        conn = self.factory.create()
        try:
            network = conn.network.get_network(network_id)
            if not network:
                raise AppException(message="Network not found", status_code=404, error_code="network_not_found")

            subnet_details = []
            for subnet_id in getattr(network, "subnets", []) or []:
                subnet = conn.network.get_subnet(subnet_id)
                if subnet:
                    subnet_details.append(
                        SubnetSummary(
                            **serialize_resource(
                                subnet,
                                ["id", "name", "cidr", "gateway_ip", "ip_version", "enable_dhcp", "dns_nameservers"],
                            )
                        )
                    )

            return NetworkDetail(**self._serialize_network_summary(network).model_dump(), subnet_details=subnet_details)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get network: {exc}") from exc

    def create_network(self, payload: NetworkCreateRequest) -> NetworkCreateResponse:
        conn = self.factory.create()
        try:
            existing_network = conn.network.find_network(payload.name, ignore_missing=True)
            if existing_network:
                raise AppException(
                    message="Network with the same name already exists",
                    status_code=409,
                    error_code="network_conflict",
                )

            network = conn.network.create_network(
                name=payload.name,
                shared=payload.shared,
                admin_state_up=payload.admin_state_up,
            )
            subnet = conn.network.create_subnet(
                network_id=network.id,
                cidr=payload.cidr,
                ip_version=payload.ip_version,
                name=payload.subnet_name or f"{payload.name}-subnet",
                gateway_ip=payload.gateway_ip,
                enable_dhcp=payload.enable_dhcp,
                dns_nameservers=payload.dns_nameservers,
            )
            return NetworkCreateResponse(network_id=network.id, subnet_id=subnet.id, name=payload.name)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create network: {exc}") from exc

    def delete_network(self, network_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.network.delete_network(network_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Network not found", status_code=404, error_code="network_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete network: {exc}") from exc

    def _serialize_network_summary(self, network: object) -> NetworkSummary:
        return NetworkSummary(
            **serialize_resource(
                network,
                ["id", "name", "status", "subnets", "admin_state_up", "shared", "is_router_external"],
            )
        )
