"""OpenStack API response cache — TTL-based in-memory with metrics.

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

    from app.common.utils.openstack_cache import openstack_cache

    # Cache a list response
    openstack_cache.set("servers", server_list)
    cached = openstack_cache.get("servers")

    # Invalidate on mutation
    openstack_cache.invalidate("servers")

    # Global metrics
    metrics = openstack_cache.collect_metrics()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from app.common.utils.cache import TTLCache, collect_cache_metrics, record_invalidation

T = TypeVar("T")

# Default TTLs (seconds) — tuned per resource type
# Overridden at startup by app.core.config.settings if provided.
DEFAULT_TTLS: dict[str, int] = {
    "servers": 5,
    "images": 30,
    "networks": 30,
    "volumes": 10,
}


def configure_from_settings() -> None:
    """Read cache TTLs from ``Settings`` and apply them to the global defaults.

    Call once at application startup so environment variables can override
    the built-in defaults.
    """
    from app.core.config.settings import get_settings

    settings = get_settings()
    overrides = {
        "servers": settings.cache_ttl_servers,
        "images": settings.cache_ttl_images,
        "networks": settings.cache_ttl_networks,
        "volumes": settings.cache_ttl_volumes,
    }
    for resource, ttl in overrides.items():
        DEFAULT_TTLS[resource] = ttl
        if resource in _instances:
            _instances[resource]._ttl = float(ttl)

# Singleton cache instances per resource type
_instances: dict[str, TTLCache[Any]] = {}


def _get_cache(resource: str) -> TTLCache[Any]:
    if resource not in _instances:
        ttl = DEFAULT_TTLS.get(resource, 30)
        _instances[resource] = TTLCache[Any](ttl_seconds=ttl, name=resource)
    return _instances[resource]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def cache_get(resource: str) -> list[Any] | None:
    """Return the cached list for *resource*, or ``None`` on miss/expiry."""
    return _get_cache(resource).get(resource)


def cache_set(resource: str, value: list[Any]) -> None:
    """Store *value* in the cache for *resource* using its default TTL."""
    _get_cache(resource).set(resource, value)


def cache_invalidate(resource: str) -> None:
    """Invalidate the cached entry for a single *resource*."""
    cache = _get_cache(resource)
    cache.invalidate_all()
    record_invalidation(resource)


def cache_invalidate_all() -> None:
    """Invalidate all OpenStack caches (use sparingly — heavyweight)."""
    for resource in list(_instances):
        cache_invalidate(resource)


def collect_metrics() -> dict[str, Any]:
    """Return a snapshot of cache hit/miss/invalidation counters."""
    return collect_cache_metrics()


def get_ttl(resource: str) -> int:
    return DEFAULT_TTLS.get(resource, 30)


def set_ttl(resource: str, ttl_seconds: int) -> None:
    DEFAULT_TTLS[resource] = ttl_seconds


def get_cache_status() -> dict[str, Any]:
    """Return per-resource cache size and TTL for observability."""
    return {
        name: {
            "ttl_seconds": DEFAULT_TTLS.get(name, 30),
            "size": cache.size,
        }
        for name, cache in _instances.items()
    }
