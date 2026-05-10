from collections.abc import Mapping

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.cache import TTLCache
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.compute import ServerActionResponse, ServerCreateRequest, ServerDetail, ServerSummary


class ComputeService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        settings = get_settings()
        self._image_cache = TTLCache[str](ttl_seconds=settings.cache_ttl_seconds)
        self._flavor_cache = TTLCache[str](ttl_seconds=settings.cache_ttl_seconds)

    def list_servers(self) -> list[ServerSummary]:
        conn = self.factory.create()
        try:
            servers = conn.compute.servers()
            return [self._serialize_server_summary(server) for server in servers]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list servers: {exc}") from exc

    def get_server(self, server_id: str) -> ServerDetail:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            return self._serialize_server_detail(server)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get server: {exc}") from exc

    def create_server(self, payload: ServerCreateRequest) -> ServerSummary:
        conn = self.factory.create()
        try:
            # Use direct get_* lookups instead of find_* (which lists ALL
            # resources and filters in Python — O(n) vs O(1)).
            image = conn.image.get_image(payload.image_id)
            if not image:
                raise AppException(message="Image not found", status_code=404, error_code="image_not_found")

            flavor = conn.compute.get_flavor(payload.flavor_id)
            if not flavor:
                raise AppException(message="Flavor not found", status_code=404, error_code="flavor_not_found")

            network = conn.network.get_network(payload.network_id)
            if not network:
                raise AppException(message="Network not found", status_code=404, error_code="network_not_found")

            if payload.key_name:
                keypair = conn.compute.get_keypair(payload.key_name)
                if not keypair:
                    raise AppException(message="Key pair not found", status_code=404, error_code="keypair_not_found")

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

            server = conn.compute.create_server(**create_kwargs)
            if payload.wait:
                server = conn.compute.wait_for_server(server)
            return self._serialize_server_summary(server)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create server: {exc}") from exc

    def perform_action(self, server_id: str, action: str) -> ServerActionResponse:
        conn = self.factory.create()

        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")

            if action == "start":
                conn.compute.start_server(server)
            elif action == "stop":
                conn.compute.stop_server(server)
            elif action == "reboot":
                conn.compute.reboot_server(server)
            else:
                raise AppException(message="Unsupported action", status_code=400, error_code="invalid_action")

            return ServerActionResponse(server_id=server_id, action=action, accepted=True)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to execute server action '{action}': {exc}") from exc

    def delete_server(self, server_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.compute.delete_server(server_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete server: {exc}") from exc

    def resize_server(self, server_id: str, flavor_id: str) -> None:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            
            conn.compute.resize_server(server, flavor_id)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to resize server: {exc}") from exc

    def confirm_resize(self, server_id: str) -> None:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            
            conn.compute.confirm_server_resize(server)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to confirm server resize: {exc}") from exc

    def revert_resize(self, server_id: str) -> None:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            
            conn.compute.revert_server_resize(server)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to revert server resize: {exc}") from exc

    def create_server_image(self, server_id: str, name: str) -> str:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            
            image_id = conn.compute.create_server_image(server, name=name)
            return image_id
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create server image snapshot: {exc}") from exc

    def attach_volume(self, server_id: str, volume_id: str) -> None:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            
            volume = conn.block_storage.get_volume(volume_id)
            if not volume:
                raise AppException(message="Volume not found", status_code=404, error_code="volume_not_found")

            conn.compute.create_volume_attachment(server, volumeId=volume.id)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to attach volume to server: {exc}") from exc

    def detach_volume(self, server_id: str, volume_id: str) -> None:
        conn = self.factory.create()
        try:
            server = conn.compute.get_server(server_id)
            if not server:
                raise AppException(message="Server not found", status_code=404, error_code="server_not_found")
            
            attachment = next((a for a in conn.compute.volume_attachments(server) if a.volume_id == volume_id), None)
            if not attachment:
                raise AppException(message="Volume attachment not found", status_code=404, error_code="attachment_not_found")
                
            conn.compute.delete_volume_attachment(attachment, server)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to detach volume from server: {exc}") from exc

    def _serialize_server_summary(self, server: object) -> ServerSummary:
        data = serialize_resource(server, ["id", "name", "status", "created", "key_name", "project_id", "availability_zone"])
        return ServerSummary(
            **data,
            flavor_id=self._extract_reference_id(getattr(server, "flavor", None)),
            image_id=self._extract_reference_id(getattr(server, "image", None)),
            addresses=self._extract_addresses(getattr(server, "addresses", None)),
        )

    def _serialize_server_detail(self, server: object) -> ServerDetail:
        summary = self._serialize_server_summary(server)
        metadata = self._extract_string_mapping(getattr(server, "metadata", None))
        return ServerDetail(**summary.model_dump(), updated=getattr(server, "updated", None), metadata=metadata)

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
