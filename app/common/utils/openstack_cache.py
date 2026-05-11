"""OpenStack API response cache — backend-agnostic (memory or Redis).

Reduces Nova/Glance/Neutron/Cinder call frequency by caching list
responses for configurable durations.  Each resource type has its own
TTL tuned to its expected churn rate:

+----------+-------+----------------------------------------+
| Resource | TTL   | Rationale                              |
+----------+-------+----------------------------------------+
| servers  |   5 s | VM state changes frequently (active /   |
|          |       | shutoff, create/delete)                 |
| images   |  30 s | Image catalog is relatively stable      |
| networks |  30 s | Network topology changes infrequently   |
| volumes  |  10 s | Volume attach/detach can happen often   |
+----------+-------+----------------------------------------+

Usage::

    from app.common.utils.openstack_cache import cache_get, cache_set, cache_invalidate

    cached = cache_get("servers")
    cache_invalidate("servers")
    metrics = collect_metrics()
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.core.config.settings import get_settings

logger = logging.getLogger("vmachine.openstack_cache")

# ---------------------------------------------------------------------------
# Default TTLs (seconds) — tuned per resource type
# ---------------------------------------------------------------------------
DEFAULT_TTLS: dict[str, int] = {
    "servers": 5,
    "images": 30,
    "networks": 30,
    "volumes": 10,
}

# ---------------------------------------------------------------------------
# CacheBackend Protocol — all backends must implement this interface
# ---------------------------------------------------------------------------


class CacheBackend(Protocol):
    """Interface that all cache backends implement.

    Memory and Redis backends both conform to this protocol so the
    dispatch layer never needs to know which backend is active.
    """

    def get(self, resource: str) -> list[Any] | None: ...
    def set(self, resource: str, value: list[Any]) -> None: ...
    def invalidate(self, resource: str) -> None: ...
    def invalidate_all(self) -> None: ...
    def collect_metrics(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Memory cache backend — wraps per-resource TTLCache instances
# ---------------------------------------------------------------------------


class MemoryCacheBackend:
    """In-memory cache backed by one ``TTLCache`` per resource type.

    Metrics (hits, misses, invalidations) are accumulated in module-level
    counters inside ``app.common.utils.cache`` and collected via
    ``collect_metrics()``.
    """

    def __init__(self, ttls: dict[str, int]) -> None:
        from app.common.utils.cache import TTLCache, collect_cache_metrics

        self._collect_metrics = collect_cache_metrics
        self._stores: dict[str, TTLCache[Any]] = {}
        for resource, ttl in ttls.items():
            self._stores[resource] = TTLCache[Any](ttl_seconds=ttl, name=resource)

    def get(self, resource: str) -> list[Any] | None:
        store = self._stores.get(resource)
        if store is None:
            return None
        return store.get(resource)

    def set(self, resource: str, value: list[Any]) -> None:
        store = self._stores.get(resource)
        if store is not None:
            store.set(resource, value)

    def invalidate(self, resource: str) -> None:
        store = self._stores.get(resource)
        if store is not None:
            store.invalidate_all()

    def invalidate_all(self) -> None:
        for store in self._stores.values():
            store.invalidate_all()

    def collect_metrics(self) -> dict[str, Any]:
        return self._collect_metrics()

    @property
    def stores(self) -> dict[str, Any]:
        return dict(self._stores)


# ---------------------------------------------------------------------------
# Backend singleton (set once at startup)
# ---------------------------------------------------------------------------
_backend: CacheBackend | None = None


def is_redis() -> bool:
    from app.common.utils.redis_cache import RedisCache

    return isinstance(_backend, RedisCache)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def configure_from_settings() -> None:
    settings = get_settings()
    for resource in ("servers", "images", "networks", "volumes"):
        ttl = getattr(settings, f"cache_ttl_{resource}", None)
        if ttl is not None:
            DEFAULT_TTLS[resource] = ttl
    init_cache_backend(
        settings.cache_backend, settings.redis_url, settings.openstack_project_name
    )


def init_cache_backend(
    backend: str, redis_url: str = "", project_name: str = "admin"
) -> None:
    """Create the cache backend singleton.

    Parameters
    ----------
    backend : str
        ``"memory"`` (default) or ``"redis"``.
    redis_url : str
        Redis connection URL (ignored for memory backend).
    project_name : str
        OpenStack project name used as Redis key namespace.
    """
    global _backend

    if backend == "redis" and redis_url:
        try:
            from app.common.utils.redis_cache import RedisCache

            _backend = RedisCache(redis_url, project_name)
            logger.info("Cache backend: Redis (%s)", redis_url)
            return
        except Exception as exc:
            logger.warning("Redis init failed (%s), falling back to memory cache", exc)

    _backend = MemoryCacheBackend(DEFAULT_TTLS)
    logger.info("Cache backend: in-memory TTLCache")


# ---------------------------------------------------------------------------
# Public API  (service layer imports these — never changes)
# ---------------------------------------------------------------------------


def cache_get(resource: str) -> list[Any] | None:
    if _backend is not None:
        return _backend.get(resource)
    return None


def cache_set(resource: str, value: list[Any]) -> None:
    if _backend is not None:
        _backend.set(resource, value)


def cache_invalidate(resource: str) -> None:
    if _backend is not None:
        _backend.invalidate(resource)


def cache_invalidate_all() -> None:
    for resource in ("servers", "images", "networks", "volumes"):
        cache_invalidate(resource)


def collect_metrics() -> dict[str, Any]:
    if _backend is not None:
        return _backend.collect_metrics()
    return {
        "hits": {},
        "misses": {},
        "invalidations": {},
        "total_hits": 0,
        "total_misses": 0,
        "total_requests": 0,
        "hit_ratio": 0.0,
    }


def get_ttl(resource: str) -> int:
    return DEFAULT_TTLS.get(resource, 30)


def set_ttl(resource: str, ttl_seconds: int) -> None:
    DEFAULT_TTLS[resource] = ttl_seconds


def get_cache_status() -> dict[str, Any]:
    info: dict[str, Any] = {
        "backend": "redis" if is_redis() else "memory",
        "ttls": dict(DEFAULT_TTLS),
    }
    if not is_redis() and isinstance(_backend, MemoryCacheBackend):
        info["resources"] = {
            name: {"ttl_seconds": DEFAULT_TTLS.get(name, 30), "size": store.size}
            for name, store in _backend.stores.items()
        }
    return info
