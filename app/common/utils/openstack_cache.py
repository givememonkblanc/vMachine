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

    # Cache a list response (backend-agnostic)
    openstack_cache_invalidate("servers")

    cached = cache_get("servers")

    # Invalidate on mutation
    cache_invalidate("servers")

    # Global metrics
    metrics = collect_cache_metrics()
"""

from __future__ import annotations

import logging
from typing import Any

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
# Backend instance (set once at startup by ``init_cache_backend()``)
# ---------------------------------------------------------------------------
_backend: Any = None  # TTLCache per-resource dict | RedisCache
_backend_type: str = "memory"  # "memory" | "redis"


def configure_from_settings() -> None:
    """Read cache TTLs and backend type from ``Settings``, then initialise.

    Call once at application startup so environment variables can override
    the built-in defaults.
    """
    settings = get_settings()
    # Apply TTL overrides
    overrides = {
        "servers": settings.cache_ttl_servers,
        "images": settings.cache_ttl_images,
        "networks": settings.cache_ttl_networks,
        "volumes": settings.cache_ttl_volumes,
    }
    for resource, ttl in overrides.items():
        DEFAULT_TTLS[resource] = ttl

    # Initialise the selected backend
    init_cache_backend(settings.cache_backend, settings.redis_url, settings.openstack_project_name)


def init_cache_backend(backend: str, redis_url: str = "", project_name: str = "admin") -> None:
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
    global _backend, _backend_type

    if backend == "redis" and redis_url:
        try:
            from app.common.utils.redis_cache import RedisCache

            _backend = RedisCache(redis_url, project_name)
            _backend_type = "redis"
            logger.info("Cache backend: Redis (%s)", redis_url)
            return
        except Exception as exc:
            logger.warning(
                "Redis init failed (%s), falling back to memory cache", exc
            )

    # Fallback: in-memory TTLCache (one per resource)
    from app.common.utils.cache import TTLCache

    _instances: dict[str, Any] = {}
    for resource, ttl in DEFAULT_TTLS.items():
        _instances[resource] = TTLCache[Any](ttl_seconds=ttl, name=resource)
    _backend = _instances
    _backend_type = "memory"
    logger.info("Cache backend: in-memory TTLCache")


def is_redis() -> bool:
    return _backend_type == "redis"


# ---------------------------------------------------------------------------
# Public API  (unchanged — service layer imports these)
# ---------------------------------------------------------------------------


def cache_get(resource: str) -> list[Any] | None:
    """Return the cached list for *resource*, or ``None`` on miss/expiry."""
    if _backend_type == "redis":
        return _backend.get(resource)
    # Memory backend: TTLCache per resource
    cache = _backend.get(resource)
    if cache is None:
        return None
    return cache.get(resource)


def cache_set(resource: str, value: list[Any]) -> None:
    """Store *value* in the cache for *resource* using its default TTL."""
    if _backend_type == "redis":
        _backend.set(resource, value)
    else:
        _backend.get(resource).set(resource, value)


def cache_invalidate(resource: str) -> None:
    """Invalidate the cached entry for a single *resource*."""
    if _backend_type == "redis":
        _backend.invalidate(resource)
    else:
        cache = _backend.get(resource)
        if cache:
            cache.invalidate_all()
            from app.common.utils.cache import record_invalidation
            record_invalidation(resource)


def cache_invalidate_all() -> None:
    """Invalidate all OpenStack caches (use sparingly — heavyweight)."""
    for resource in ("servers", "images", "networks", "volumes"):
        cache_invalidate(resource)


def collect_metrics() -> dict[str, Any]:
    """Return a snapshot of cache hit/miss/invalidation counters."""
    from app.common.utils.cache import collect_cache_metrics as _collect_mem

    if _backend_type == "redis":
        return _backend.collect_metrics()
    return _collect_mem()


def get_ttl(resource: str) -> int:
    return DEFAULT_TTLS.get(resource, 30)


def set_ttl(resource: str, ttl_seconds: int) -> None:
    DEFAULT_TTLS[resource] = ttl_seconds


def get_cache_status() -> dict[str, Any]:
    """Return per-resource cache size and TTL for observability."""
    if _backend_type == "redis":
        return {"backend": "redis", "ttls": dict(DEFAULT_TTLS)}
    return {
        "backend": "memory",
        "ttls": dict(DEFAULT_TTLS),
        "resources": {
            name: {
                "ttl_seconds": DEFAULT_TTLS.get(name, 30),
                "size": cache.size,
            }
            for name, cache in (_backend or {}).items()
        },
    }
