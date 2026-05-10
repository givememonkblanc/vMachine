from importlib import import_module
from typing import Protocol, cast

from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.core.config.settings import Settings


class ConnectionConstructor(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class OpenStackConnectionFactory:
    def __init__(self, settings: Settings):
        self.settings: Settings = settings

    def create(self) -> object:
        if not self.settings.openstack_ready:
            raise AppException(
                message="OpenStack settings are incomplete. Fill the required OPENSTACK_* environment variables.",
                status_code=503,
                error_code="openstack_not_configured",
            )

        try:
            connection_module = import_module("openstack.connection")
            connection_class = cast(ConnectionConstructor, getattr(connection_module, "Connection"))
            return connection_class(
                auth_url=self.settings.openstack_auth_url,
                username=self.settings.openstack_username,
                password=self.settings.openstack_password,
                project_name=self.settings.openstack_project_name,
                user_domain_name=self.settings.openstack_user_domain_name,
                project_domain_name=self.settings.openstack_project_domain_name,
                region_name=self.settings.openstack_region_name,
                interface=self.settings.openstack_interface,
                verify=self.settings.openstack_verify_ssl,
                app_name=self.settings.app_name,
                app_version="0.1.0",
            )
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create OpenStack connection: {exc}") from exc
