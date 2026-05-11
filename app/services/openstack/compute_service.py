from collections.abc import Mapping

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.common.utils.cache import TTLCache
from app.common.utils.openstack_cache import cache_get, cache_invalidate, cache_set
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.compute import (
    ServerActionResponse,
    ServerCreateRequest,
    ServerDetail,
    ServerSummary,
)


class ComputeService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        settings = get_settings()
        self._image_cache = TTLCache[str](ttl_seconds=settings.cache_ttl_seconds)
        self._flavor_cache = TTLCache[str](ttl_seconds=settings.cache_ttl_seconds)
        self._list_limit = settings.openstack_list_limit

    def list_servers(self) -> list[ServerSummary]:
        cached = cache_get("servers")
        if cached is not None:
            return cached
        servers = self.factory.call("compute", "servers", limit=self._list_limit)
        result = [self._serialize_server_summary(server) for server in servers]
        cache_set("servers", result)
        return result

    def get_server(self, server_id: str) -> ServerDetail:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )
        return self._serialize_server_detail(server)

    def create_server(self, payload: ServerCreateRequest) -> ServerSummary:
        image = self.factory.call("image", "get_image", payload.image_id)
        if not image:
            raise AppException(
                message="Image not found", status_code=404, error_code="image_not_found"
            )

        flavor = self.factory.call("compute", "get_flavor", payload.flavor_id)
        if not flavor:
            raise AppException(
                message="Flavor not found",
                status_code=404,
                error_code="flavor_not_found",
            )

        network = self.factory.call("network", "get_network", payload.network_id)
        if not network:
            raise AppException(
                message="Network not found",
                status_code=404,
                error_code="network_not_found",
            )

        if payload.key_name:
            keypair = self.factory.call("compute", "get_keypair", payload.key_name)
            if not keypair:
                raise AppException(
                    message="Key pair not found",
                    status_code=404,
                    error_code="keypair_not_found",
                )

        create_kwargs: dict[str, object] = {
            "name": payload.name,
            "image_id": payload.image_id,
            "flavor_id": payload.flavor_id,
            "networks": [{"uuid": payload.network_id}],
            "metadata": payload.metadata,
        }
        if payload.key_name:
            create_kwargs["key_name"] = payload.key_name
        if payload.availability_zone:
            create_kwargs["availability_zone"] = payload.availability_zone

        server = self.factory.call("compute", "create_server", **create_kwargs)
        if payload.wait:
            server = self.factory.call("compute", "wait_for_server", server)
        cache_invalidate("servers")
        return self._serialize_server_summary(server)

    def perform_action(self, server_id: str, action: str) -> ServerActionResponse:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )

        action_map = {
            "start": "start_server",
            "stop": "stop_server",
            "reboot": "reboot_server",
        }
        sdk_action = action_map.get(action)
        if sdk_action is None:
            raise AppException(
                message="Unsupported action",
                status_code=400,
                error_code="invalid_action",
            )

        self.factory.call("compute", sdk_action, server)
        return ServerActionResponse(server_id=server_id, action=action, accepted=True)

    def delete_server(self, server_id: str) -> None:
        deleted = self.factory.call(
            "compute", "delete_server", server_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )
        cache_invalidate("servers")

    def resize_server(self, server_id: str, flavor_id: str) -> None:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )
        self.factory.call("compute", "resize_server", server, flavor_id)

    def confirm_resize(self, server_id: str) -> None:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )
        self.factory.call("compute", "confirm_server_resize", server)

    def revert_resize(self, server_id: str) -> None:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )
        self.factory.call("compute", "revert_server_resize", server)

    def create_server_image(self, server_id: str, name: str) -> str:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )
        return self.factory.call("compute", "create_server_image", server, name=name)

    def attach_volume(self, server_id: str, volume_id: str) -> None:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )

        volume = self.factory.call("block_storage", "get_volume", volume_id)
        if not volume:
            raise AppException(
                message="Volume not found",
                status_code=404,
                error_code="volume_not_found",
            )

        self.factory.call(
            "compute", "create_volume_attachment", server, volumeId=volume.id
        )
        cache_invalidate("servers")
        cache_invalidate("volumes")

    def detach_volume(self, server_id: str, volume_id: str) -> None:
        server = self.factory.call("compute", "get_server", server_id)
        if not server:
            raise AppException(
                message="Server not found",
                status_code=404,
                error_code="server_not_found",
            )

        attachments = self.factory.call("compute", "volume_attachments", server)
        attachment = next((a for a in attachments if a.volume_id == volume_id), None)
        if not attachment:
            raise AppException(
                message="Volume attachment not found",
                status_code=404,
                error_code="attachment_not_found",
            )

        self.factory.call("compute", "delete_volume_attachment", attachment, server)
        cache_invalidate("servers")
        cache_invalidate("volumes")

    def _serialize_server_summary(self, server: object) -> ServerSummary:
        data = serialize_resource(
            server,
            [
                "id",
                "name",
                "status",
                "created",
                "key_name",
                "project_id",
                "availability_zone",
            ],
        )
        return ServerSummary(
            **data,
            flavor_id=self._extract_reference_id(getattr(server, "flavor", None)),
            image_id=self._extract_reference_id(getattr(server, "image", None)),
            addresses=self._extract_addresses(getattr(server, "addresses", None)),
        )

    def _serialize_server_detail(self, server: object) -> ServerDetail:
        summary = self._serialize_server_summary(server)
        metadata = self._extract_string_mapping(getattr(server, "metadata", None))
        return ServerDetail(
            **summary.model_dump(),
            updated=getattr(server, "updated", None),
            metadata=metadata,
        )

    def _extract_reference_id(self, value: object) -> str | None:
        if isinstance(value, Mapping):
            reference_id = value.get("id")
            return str(reference_id) if reference_id is not None else None
        reference_id = getattr(value, "id", None)
        return str(reference_id) if reference_id is not None else None

    def _extract_addresses(self, value: object) -> dict[str, list[str]]:
        if not isinstance(value, Mapping):
            return {}
        addresses: dict[str, list[str]] = {}
        for network_name, entries in value.items():
            if not isinstance(network_name, str) or not isinstance(entries, list):
                continue
            ips: list[str] = []
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                ip_address = entry.get("addr")
                if isinstance(ip_address, str):
                    ips.append(ip_address)
            addresses[network_name] = ips
        return addresses

    def _extract_string_mapping(self, value: object) -> dict[str, str]:
        if not isinstance(value, Mapping):
            return {}
        return {str(key): str(item) for key, item in value.items()}
