from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import OpenStackIntegrationException
from app.schemas.identity.auth import (
    OpenStackServiceCatalogResponse,
    OpenStackServiceEndpoint,
    OpenStackTokenInfo,
    OpenStackValidationResponse,
)


class AuthService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def get_token_info(self) -> OpenStackTokenInfo:
        settings = self.factory.settings
        return OpenStackTokenInfo(
            configured=settings.openstack_ready,
            auth_url=settings.openstack_auth_url or None,
            region_name=settings.openstack_region_name or None,
            interface=settings.openstack_interface or None,
            project_name=settings.openstack_project_name or None,
            user_name=settings.openstack_username or None,
        )

    def validate_connection(self) -> OpenStackValidationResponse:
        conn = self.factory.create()
        try:
            authenticated = conn.authorize()
        except Exception as exc:
            raise OpenStackIntegrationException(f"OpenStack authorization failed: {exc}") from exc

        if not authenticated:
            raise OpenStackIntegrationException("OpenStack authorization failed")

        settings = self.factory.settings
        session = conn.session
        token = session.get_token()
        return OpenStackValidationResponse(
            connected=True,
            region_name=settings.openstack_region_name,
            project_name=settings.openstack_project_name,
            user_name=settings.openstack_username,
            interface=settings.openstack_interface,
            project_id=session.get_project_id(),
            user_id=session.get_user_id(),
            token_preview=self._redact_token(token),
        )

    def get_service_catalog(self) -> OpenStackServiceCatalogResponse:
        conn = self.factory.create()
        try:
            conn.authorize()
            session = conn.session
            settings = self.factory.settings
            items = [
                OpenStackServiceEndpoint(
                    service_type=service_type,
                    url=self._get_endpoint_url(session, service_type, settings.openstack_interface, settings.openstack_region_name),
                )
                for service_type in ["identity", "image", "compute", "network", "volumev3", "placement"]
            ]
            return OpenStackServiceCatalogResponse(items=items)
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to load OpenStack service catalog: {exc}") from exc

    def _get_endpoint_url(
        self,
        session: object,
        service_type: str,
        interface: str,
        region_name: str,
    ) -> str | None:
        try:
            return session.get_endpoint(
                service_type=service_type,
                interface=interface,
                region_name=region_name,
            )
        except Exception:
            return None

    def _redact_token(self, token: str | None) -> str | None:
        if not token:
            return None
        if len(token) <= 10:
            return token
        return f"{token[:6]}...{token[-4:]}"
