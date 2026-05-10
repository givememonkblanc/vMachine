from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.schemas.openstack.keypair import KeypairCreateRequest, KeypairSummary


class KeypairService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_keypairs(self) -> list[KeypairSummary]:
        return [
            KeypairSummary(
                name=kp.name,
                fingerprint=getattr(kp, "fingerprint", ""),
                type=getattr(kp, "type", "ssh"),
            )
            for kp in self.factory.call("compute", "keypairs")
        ]

    def get_keypair(self, keypair_name: str) -> KeypairSummary:
        kp = self.factory.call("compute", "find_keypair", keypair_name, ignore_missing=True)
        if not kp:
            raise AppException(message="Keypair not found", status_code=404, error_code="keypair_not_found")
        return KeypairSummary(name=kp.name, fingerprint=getattr(kp, "fingerprint", ""), type=getattr(kp, "type", "ssh"))

    def create_keypair(self, payload: KeypairCreateRequest) -> KeypairSummary:
        existing = self.factory.call("compute", "find_keypair", payload.name, ignore_missing=True)
        if existing:
            raise AppException(
                message=f"Keypair '{payload.name}' already exists",
                status_code=409,
                error_code="keypair_already_exists",
            )
        kwargs: dict[str, object] = {"name": payload.name, "type": payload.type or "ssh"}
        if payload.public_key:
            kwargs["public_key"] = payload.public_key
        kp = self.factory.call("compute", "create_keypair", **kwargs)
        return KeypairSummary(
            name=kp.name,
            fingerprint=getattr(kp, "fingerprint", ""),
            type=getattr(kp, "type", "ssh"),
        )

    def delete_keypair(self, keypair_name: str) -> None:
        deleted = self.factory.call("compute", "delete_keypair", keypair_name, ignore_missing=True)
        if deleted is False:
            raise AppException(message="Keypair not found", status_code=404, error_code="keypair_not_found")
