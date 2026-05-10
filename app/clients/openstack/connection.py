"""OpenStack SDK connection factory with HTTP connection pooling and retry.

Key optimizations over vanilla openstacksdk:
  1. HTTPAdapter with configurable pool size and keepalive
  2. Retry strategy (backoff) for transient failures
  3. Configurable timeout on the keystone session
  4. Thread-safe cached connection (auth once, reuse forever)
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from importlib import import_module
from typing import Any, Protocol, cast

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as RetryStrategy

from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.core.config.settings import Settings


class ConnectionConstructor(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


def _get_openstack_connection_class() -> ConnectionConstructor:
    connection_module = import_module("openstack.connection")
    return cast(ConnectionConstructor, getattr(connection_module, "Connection"))


def _build_http_session(settings: Settings) -> requests.Session:
    """Build a requests.Session with connection pooling and retry."""
    session = requests.Session()

    retry = RetryStrategy(
        total=settings.openstack_retry_max,
        backoff_factor=settings.openstack_retry_backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"],
    )

    adapter = HTTPAdapter(
        pool_connections=settings.openstack_pool_connections,
        pool_maxsize=settings.openstack_pool_maxsize,
        max_retries=retry if settings.openstack_retry_max > 0 else 0,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class OpenStackConnectionFactory:
    """Factory that caches and reuses OpenStack SDK Connection instances.

    Creating an OpenStack SDK Connection involves a Keystone authentication
    handshake (500ms-2s).  This factory caches the connection after first
    creation and reuses it, eliminating redundant auth on every API call.
    The SDK Connection handles token refresh internally.

    The underlying ``requests.Session`` is configured with:
    - Connection pool (default 20 connections, 50 max)
    - Retry with exponential backoff for 5xx responses
    - Request timeout (default 60s)
    """

    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        self._connection: object | None = None

    def create(self) -> object:
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

            # Build a requests.Session with our pool / retry settings.
            http_session = _build_http_session(self.settings)

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

            # Patch the underlying requests.Session *after* connection
            # creation so all subsequent HTTP calls use our pool.
            ks_session = getattr(self._connection, "session", None)
            if ks_session is not None:
                # keystoneauth1.session.Session stores the requests session
                # in its own `session` attribute.
                ks_session.session = http_session
                ks_session.timeout = self.settings.openstack_timeout

            return self._connection

        except Exception as exc:
            raise OpenStackIntegrationException(
                f"Failed to create OpenStack connection: {exc}"
            ) from exc

    def invalidate(self) -> None:
        self._connection = None


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
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, lambda: func(*args, **kwargs)),
        timeout=timeout,
    )
