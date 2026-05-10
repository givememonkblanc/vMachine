from collections.abc import Callable
from functools import wraps
from importlib import import_module
from typing import Any, Protocol, cast

from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.core.config.settings import Settings


class ConnectionConstructor(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


def _get_openstack_connection_class() -> ConnectionConstructor:
    """Lazy-load the OpenStack SDK Connection class."""
    connection_module = import_module("openstack.connection")
    return cast(ConnectionConstructor, getattr(connection_module, "Connection"))


class OpenStackConnectionFactory:
    """Factory that caches and reuses OpenStack SDK Connection instances.

    Creating an OpenStack SDK Connection involves a Keystone authentication
    handshake (500ms-2s).  This factory caches the connection after first
    creation and reuses it, eliminating redundant auth on every API call.
    The SDK Connection handles token refresh internally.
    """

    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        self._connection: object | None = None

    def create(self) -> object:
        """Return a cached OpenStack connection, creating one if necessary."""
        if self._connection is not None:
            return self._connection

        if not self.settings.openstack_ready:
            raise AppException(
                message="OpenStack settings are incomplete. Fill the required OPENSTACK_* environment variables.",
                status_code=503,
                error_code="openstack_not_configured",
            )

        try:
            connection_class = _get_openstack_connection_class()
            self._connection = connection_class(
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
            return self._connection
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create OpenStack connection: {exc}") from exc

    def invalidate(self) -> None:
        """Force re-creation of the connection on the next ``create()`` call.

        Use after network partitions, long idle periods, or settings changes.
        """
        self._connection = None


# ---------------------------------------------------------------------------
# Timeout helper for blocking OpenStack SDK calls
# ---------------------------------------------------------------------------

async def call_with_timeout(
    func: Callable[..., Any],
    *args: Any,
    timeout: float = 30.0,
    **kwargs: Any,
) -> Any:
    """Run a synchronous blocking call in a thread pool with a timeout.

    OpenStack SDK calls are synchronous and block the event loop.
    This wrapper runs them off the main thread and raises
    ``asyncio.TimeoutError`` if the call exceeds *timeout* seconds.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, lambda: func(*args, **kwargs)),
        timeout=timeout,
    )
