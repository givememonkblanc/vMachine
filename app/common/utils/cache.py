"""Simple TTL cache for frequently-accessed but rarely-changed resources.

Usage::

    cache = TTLCache[str](ttl_seconds=300)
    item = cache.get("my_key")
    if item is None:
        item = fetch_expensive_data()
        cache.set("my_key", item)
"""

from time import monotonic, time as time_now
from typing import Generic, TypeVar

T = TypeVar("T")


class _CacheEntry(Generic[T]):
    __slots__ = ("value", "expires_at")

    def __init__(self, value: T, ttl_seconds: float) -> None:
        self.value = value
        self.expires_at = time_now() + ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time_now() >= self.expires_at


class TTLCache(Generic[T]):
    """In-memory cache with per-entry time-to-live expiration.

    Thread-safe for single-threaded async contexts.  Not safe for
    concurrent writes from multiple threads.
    """

    def __init__(self, ttl_seconds: int | float = 300) -> None:
        self._ttl: float = float(ttl_seconds)
        self._store: dict[str, _CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        self._store[key] = _CacheEntry(value, self._ttl)

    def set_ttl(self, key: str, value: T, ttl_seconds: int | float) -> None:
        self._store[key] = _CacheEntry(value, float(ttl_seconds))

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def evict_expired(self) -> int:
        now = time_now()
        expired_keys = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def get_or_set(self, key: str, factory: callable) -> T:
        existing = self.get(key)
        if existing is not None:
            return existing
        value = factory()
        self.set(key, value)
        return value
