from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.openstack.keypair import KeypairCreateRequest, KeypairCreateResponse, KeypairSummary


class KeypairService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_keypairs(self) -> list[KeypairSummary]:
        conn = self.factory.create()
        try:
            return [
                KeypairSummary(**serialize_resource(keypair, ["name", "public_key", "fingerprint"]))
                for keypair in conn.compute.keypairs()
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list keypairs: {exc}") from exc

    def get_keypair(self, keypair_name: str) -> KeypairSummary:
        conn = self.factory.create()
        try:
            keypair = conn.compute.find_keypair(keypair_name, ignore_missing=True)
            if not keypair:
                raise AppException(message="Keypair not found", status_code=404, error_code="keypair_not_found")
            return KeypairSummary(**serialize_resource(keypair, ["name", "public_key", "fingerprint"]))
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get keypair: {exc}") from exc

    def create_keypair(self, payload: KeypairCreateRequest) -> KeypairCreateResponse:
        conn = self.factory.create()
        try:
            existing = conn.compute.find_keypair(payload.name, ignore_missing=True)
            if existing:
                raise AppException(
                    message="Keypair with the same name already exists",
                    status_code=409,
                    error_code="keypair_conflict",
                )

            kwargs = {"name": payload.name}
            if payload.public_key:
                kwargs["public_key"] = payload.public_key

            keypair = conn.compute.create_keypair(**kwargs)
            return KeypairCreateResponse(
                name=keypair.name,
                public_key=keypair.public_key,
                private_key=getattr(keypair, "private_key", None),
            )
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create keypair: {exc}") from exc

    def delete_keypair(self, keypair_name: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.compute.delete_keypair(keypair_name, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Keypair not found", status_code=404, error_code="keypair_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete keypair: {exc}") from exc
