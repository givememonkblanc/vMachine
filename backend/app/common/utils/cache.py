"""TTL cache with hit/mit metrics for OpenStack API response caching.

Usage::

    cache = TTLCache[str](ttl_seconds=300)
    item = cache.get("my_key")        # tracks hits/misses
    if item is None:
        item = fetch_expensive_data()
        cache.set("my_key", item)
"""

from time import time as time_now
from typing import Any, Generic, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Global metric counters — shared across all TTLCache instances
# ---------------------------------------------------------------------------
# Internal counters; use ``collect_cache_metrics()`` for a snapshot.
_cache_hits: dict[str, int] = {}
_cache_misses: dict[str, int] = {}
_cache_invalidations: dict[str, int] = {}


def _incr(counter: dict[str, int], name: str) -> None:
    counter[name] = counter.get(name, 0) + 1


def collect_cache_metrics() -> dict[str, Any]:
    """Return a snapshot of all cache metric counters."""
    all_hits = dict(_cache_hits)
    all_misses = dict(_cache_misses)
    all_inval = dict(_cache_invalidations)
    total_hits = sum(all_hits.values())
    total_misses = sum(all_misses.values())
    total_reqs = total_hits + total_misses
    return {
        "hits": all_hits,
        "misses": all_misses,
        "invalidations": all_inval,
        "total_hits": total_hits,
        "total_misses": total_misses,
        "total_requests": total_reqs,
        "hit_ratio": round(total_hits / total_reqs, 4) if total_reqs else 0.0,
    }


def record_invalidation(cache_name: str) -> None:
    _incr(_cache_invalidations, cache_name)


# ---------------------------------------------------------------------------
# Cache entry & TTL cache
# ---------------------------------------------------------------------------


class _CacheEntry(Generic[T]):
    __slots__ = ("value", "expires_at")

    def __init__(self, value: T, ttl_seconds: float) -> None:
        self.value = value
        self.expires_at = time_now() + ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time_now() >= self.expires_at


class TTLCache(Generic[T]):
    """In-memory cache with per-entry time-to-live expiration and metrics.

    Thread-safe for single-threaded async contexts.  Not safe for
    concurrent writes from multiple threads.

    Parameters
    ----------
    ttl_seconds : int | float
        Default TTL for entries added via ``set()``.
    name : str
        Logical name used in metric labels (e.g. ``"servers"``, ``"images"``).
    """

    def __init__(self, ttl_seconds: int | float = 300, name: str = "default") -> None:
        self._ttl: float = float(ttl_seconds)
        self._name: str = name
        self._store: dict[str, _CacheEntry[T]] = {}

    # -- public API ---------------------------------------------------------

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            _incr(_cache_misses, self._name)
            return None
        if entry.is_expired:
            del self._store[key]
            _incr(_cache_misses, self._name)
            return None
        _incr(_cache_hits, self._name)
        return entry.value

    def set(self, key: str, value: T) -> None:
        self._store[key] = _CacheEntry(value, self._ttl)

    def set_ttl(self, key: str, value: T, ttl_seconds: int | float) -> None:
        self._store[key] = _CacheEntry(value, float(ttl_seconds))

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def invalidate_all(self) -> None:
        """Clear the entire cache and bump the invalidation counter."""
        self._store.clear()
        _incr(_cache_invalidations, self._name)

    # -- introspection -----------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> int:
        return len(self._store)

    def evict_expired(self) -> int:
        now = time_now()
        expired_keys = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)
