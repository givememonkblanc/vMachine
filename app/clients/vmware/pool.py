from __future__ import annotations

import contextlib
import threading
import time
from typing import Any

from pyVim.connect import Disconnect, SmartConnect

from app.common.exceptions.base import AppException
from app.core.config.settings import Settings


class PooledConnection:
    """A single pooled vCenter connection wrapper."""

    def __init__(self, si: Any, created_at: float) -> None:
        self.si = si
        self.created_at = created_at
        self.last_used_at = created_at
        self.use_count = 0

    def is_alive(self) -> bool:
        try:
            self.si.CurrentTime()
            return True
        except Exception:
            return False

    def age_seconds(self, now: float | None = None) -> float:
        return (now or time.time()) - self.created_at


class VMwareConnectionPool:
    """Reusable connection pool for VMware vCenter.

    Manages a pool of ``SmartConnect`` ServiceInstance connections with:
    * Connection reuse across requests
    * Configurable session expiry
    * Automatic stale connection reconnection
    * Periodic health checking

    Thread-safe (uses ``threading.Lock``). All pool operations are fast
    synchronous calls suitable for use inside FastAPI dependency injection.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        max_pool_size: int = 4,
        session_ttl_seconds: int = 600,
        health_check_interval: int = 60,
    ) -> None:
        self.settings = settings
        self.max_pool_size = max_pool_size
        self.session_ttl = session_ttl_seconds
        self.health_check_interval = health_check_interval

        self._lock = threading.Lock()
        self._pool: list[PooledConnection] = []
        self._last_health_check: float = 0.0

        # Metrics
        self.conn_created: int = 0
        self.conn_reused: int = 0
        self.conn_reconnected: int = 0
        self.conn_failed: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self) -> PooledConnection:
        """Get a healthy connection from the pool (or create one)."""
        self._health_check_if_needed()

        with self._lock:
            healthy = self._find_healthy()

            if healthy is not None:
                healthy.use_count += 1
                healthy.last_used_at = time.time()
                self.conn_reused += 1
                return healthy

        return self._create_new()

    @contextlib.contextmanager
    def connection(self) -> Any:
        """Context manager — yields a raw ServiceInstance."""
        pc = self.acquire()
        try:
            yield pc.si
        except Exception:
            self._eject(pc)
            raise

    def disconnect_all(self) -> None:
        with self._lock:
            for pc in self._pool:
                try:
                    Disconnect(pc.si)
                except Exception:
                    pass
            self._pool.clear()

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pool_size": len(self._pool),
                "max_pool_size": self.max_pool_size,
                "session_ttl_seconds": self.session_ttl,
                "conn_created": self.conn_created,
                "conn_reused": self.conn_reused,
                "conn_reconnected": self.conn_reconnected,
                "conn_failed": self.conn_failed,
                "connections": [
                    {
                        "use_count": c.use_count,
                        "age_seconds": c.age_seconds(),
                        "idle_seconds": time.time() - c.last_used_at,
                    }
                    for c in self._pool
                ],
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_healthy(self) -> PooledConnection | None:
        now = time.time()
        survivors: list[PooledConnection] = []
        for pc in self._pool:
            if (now - pc.created_at) > self.session_ttl:
                self._disconnect_one(pc)
                continue
            survivors.append(pc)
        self._pool = survivors

        # Return the least-used connection
        if survivors:
            return min(survivors, key=lambda c: c.use_count)
        return None

    def _create_new(self) -> PooledConnection:
        if not self.settings.vmware_ready:
            raise AppException(
                message="VMware settings are incomplete.",
                status_code=500,
                error_code="vmware_integration_error",
            )

        try:
            t0 = time.time()
            context = None
            if self.settings.vmware_no_verify_ssl:
                import ssl

                context = ssl._create_unverified_context()
            si = SmartConnect(
                host=self.settings.vmware_host,
                user=self.settings.vmware_user,
                pwd=self.settings.vmware_password,
                sslContext=context,
            )
            created_ms = (time.time() - t0) * 1000

            pc = PooledConnection(si, created_at=t0)
            pc.use_count = 1

            with self._lock:
                if len(self._pool) < self.max_pool_size:
                    self._pool.append(pc)
                self.conn_created += 1

            # Track creation latency
            if hasattr(self, "_creation_latencies"):
                self._creation_latencies.append(created_ms)

            return pc
        except Exception as exc:
            self.conn_failed += 1
            raise AppException(
                message=f"Failed to connect to VMware: {exc}",
                status_code=500,
                error_code="vmware_integration_error",
            ) from exc

    def _eject(self, pc: PooledConnection) -> None:
        with self._lock:
            if pc in self._pool:
                self._pool.remove(pc)
        self._disconnect_one(pc)

    def _health_check_if_needed(self) -> None:
        now = time.time()
        if (now - self._last_health_check) < self.health_check_interval:
            return
        self._last_health_check = now
        with self._lock:
            for pc in list(self._pool):
                if not pc.is_alive():
                    self.conn_reconnected += 1
                    self._pool.remove(pc)
                    self._disconnect_one(pc)

    @staticmethod
    def _disconnect_one(pc: PooledConnection) -> None:
        try:
            Disconnect(pc.si)
        except Exception:
            pass
