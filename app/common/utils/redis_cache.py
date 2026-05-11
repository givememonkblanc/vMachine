"""Redis-backed distributed cache for OpenStack API responses.

Shares the same ``get``/``set``/``invalidate`` interface as the in-memory
``TTLCache`` so the service layer is backend-agnostic.

Key format: ``okastro:{project_name}:{resource}``

Usage::

    from app.common.utils.openstack_cache import cache_get, cache_set, cache_invalidate
    # No change required — backend is selected via CACHE_BACKEND env var.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis
from redis.exceptions import RedisError

logger = logging.getLogger("vmachine.redis_cache")

PROM_RESOURCE_LABELS: dict[str, str] = {
    "servers": "servers",
    "images": "images",
    "networks": "networks",
    "volumes": "volumes",
}


class RedisCache:
    """Distributed cache backed by Redis, sharing state across all workers.

    When Redis is unreachable, operations degrade silently — ``get`` returns
    ``None`` (cache miss) and ``set``/``invalidate`` are no-ops.  The
    application falls back to making live OpenStack calls.
    """

    KEY_PREFIX = "okastro"

    def __init__(self, redis_url: str, project_name: str = "admin") -> None:
        self._project = project_name
        self._client: redis.Redis = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        # Ping once to surface connection errors at init time.
        self._client.ping()
        logger.info("RedisCache connected to %s (project=%s)", redis_url, project_name)

    # ------------------------------------------------------------------
    # Metric counters (in-process, synced to Prometheus background task)
    # ------------------------------------------------------------------
    _hits: dict[str, int] = {}
    _misses: dict[str, int] = {}
    _invalidations: dict[str, int] = {}
    _errors: int = 0
    _latencies: list[float] = []  # rolling window sampled by background task

    # ------------------------------------------------------------------
    # Public API  (mirrors openstack_cache.py interface)
    # ------------------------------------------------------------------

    def get(self, resource: str) -> list[Any] | None:
        key = self._key(resource)
        try:
            t0 = time.monotonic()
            raw: str | None = self._client.get(key)  # type: ignore[assignment]
            self._record_latency(time.monotonic() - t0)
        except RedisError:
            logger.warning(
                "Redis GET %s failed, falling back to miss", key, exc_info=True
            )
            self._incr(self._misses, resource)
            self._errors += 1
            return None

        if raw is None:
            self._incr(self._misses, resource)
            return None
        self._incr(self._hits, resource)
        return self._deserialize(raw)

    def set(self, resource: str, value: list[Any]) -> None:
        key = self._key(resource)
        ttl = self._ttl_for(resource)
        try:
            t0 = time.monotonic()
            self._client.setex(key, ttl, self._serialize(value))
            self._record_latency(time.monotonic() - t0)
        except RedisError:
            logger.warning("Redis SET %s failed", key, exc_info=True)
            self._errors += 1

    def invalidate(self, resource: str) -> None:
        key = self._key(resource)
        try:
            t0 = time.monotonic()
            self._client.delete(key)
            self._record_latency(time.monotonic() - t0)
        except RedisError:
            logger.warning("Redis DEL %s failed", key, exc_info=True)
            self._errors += 1
        self._incr(self._invalidations, resource)

    def invalidate_all(self) -> None:
        for resource in ("servers", "images", "networks", "volumes"):
            self.invalidate(resource)

    def collect_metrics(self) -> dict[str, Any]:
        """Return a snapshot compatible with ``collect_cache_metrics()``."""
        h = dict(self._hits)
        m = dict(self._misses)
        v = dict(self._invalidations)
        total_h = sum(h.values())
        total_m = sum(m.values())
        return {
            "hits": h,
            "misses": m,
            "invalidations": v,
            "total_hits": total_h,
            "total_misses": total_m,
            "total_requests": total_h + total_m,
            "hit_ratio": round(total_h / (total_h + total_m), 4)
            if (total_h + total_m)
            else 0.0,
            "redis_errors": self._errors,
            "redis_latency_samples": list(self._latencies),
        }

    def close(self) -> None:
        try:
            self._client.close()
        except RedisError:
            pass

    # ------------------------------------------------------------------
    # Redis-specific helpers
    # ------------------------------------------------------------------

    def _key(self, resource: str) -> str:
        return f"{self.KEY_PREFIX}:{self._project}:{resource}"

    @staticmethod
    def _serialize(value: list[Any]) -> str:
        import json

        def _default(o: Any) -> Any:
            if hasattr(o, "model_dump"):
                return o.model_dump()
            return str(o)

        return json.dumps(value, default=_default)

    @staticmethod
    def _deserialize(raw: str) -> list[Any]:
        import json

        return json.loads(raw)

    @staticmethod
    def _ttl_for(resource: str) -> int:
        from app.common.utils.openstack_cache import DEFAULT_TTLS

        return DEFAULT_TTLS.get(resource, 30)

    # ------------------------------------------------------------------
    # Metric helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _incr(counter: dict[str, int], name: str) -> None:
        counter[name] = counter.get(name, 0) + 1

    def _record_latency(self, seconds: float) -> None:
        self._latencies.append(seconds)
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-500:]
