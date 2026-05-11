# OpenStack Connection Lifecycle

> How the OpenStack SDK connection is created, cached, refreshed, and invalidated.
> Last updated: 2026-05-11

## Architecture

```
OpenStackConnectionFactory (app/clients/openstack/connection.py)
  ├── Singleton per Gunicorn worker (cached in module-level variable)
  ├── Single cached Connection object (auth once, reuse forever)
  ├── Custom HTTP session with connection pooling + retry
  └── invalidate() method (never called in current code)

VMProvisioningEngine._nova_call()
  └── factory.create() → returns cached connection
      └── compute.<method>(*args) → synchronous SDK call
          └── call_with_timeout() → thread pool + asyncio.wait_for
```

## Connection Creation (`factory.create()`)

1. **First call**: Performs Keystone authentication (password grant) via `openstacksdk.Connection`. This involves:
   - Token request to Keystone
   - Service catalog retrieval
   - Establishing the requests.Session with configured pool/retry
   - Typical latency: 500ms–2s

2. **Subsequent calls**: Returns the cached `_connection` object immediately. No additional auth overhead.

3. **If `openstack_ready` is False** (missing env vars): Returns 503 with `openstack_not_configured` error code.

## Session & Token Management

| Concern | Behavior | Risk |
|---------|----------|------|
| **Token expiration** | Handled internally by `openstacksdk.Connection`. The SDK refreshes the token transparently when Keystone returns 401. | 🟢 Low — SDK manages this |
| **HTTP session** | Custom `requests.Session` injected after connection creation (`ks_session.session = http_session`). Pool size: 20 connections, max 50. | 🟢 Low — standard pattern |
| **Stale connection** | If the underlying SDK connection enters a bad state (e.g., network partition during token refresh), the factory has no mechanism to detect or recover. | 🟡 Medium — `invalidate()` exists but is never called |
| **Connection leak** | Single connection reused indefinitely. No connection churn. No `max_requests` or `max_age` invalidation. | 🟢 Low — connection pool handles HTTP connections |

## Thread Safety

`create()` is called from `_nova_call()` which runs inside `call_with_timeout()` → `loop.run_in_executor(None, ...)`. This means:

- Multiple lifecycle operations can call `create()` concurrently from different thread pool threads
- The `_connection` attribute is read and written without a lock
- **Race condition**: If two concurrent calls both find `_connection is None` (cold start), both will create a connection. The second assignment overwrites the first. The first connection becomes unreferenced but is still usable by whoever holds it.

**Impact**: Low — the race window is narrow (first call is ~500ms–2s) and even if both connections are created, both work. The unreferenced connection is garbage-collected. No crash, no data corruption.

**Mitigation considered but not implemented**: A `threading.Lock` around `create()` would serialize concurrent cold starts. Not implemented because the race is harmless and the window is narrow.

## `invalidate()` — Dead Code Path

The factory has an `invalidate()` method that sets `_connection = None`, forcing re-authentication on the next call. However:

- **Not called from anywhere** in the current codebase
- No mechanism detects stale connections automatically
- No periodic health check exists
- No max-connection-age policy triggers invalidation

**If a token refresh fails silently** (the SDK reports 401 but doesn't recover), the factory will continue returning the stale connection. Every subsequent API call will fail with an auth error. Manual restart of the Gunicorn worker is the only recovery path today.

## Multi-Tenant Boundary

The factory is **single-tenant**:

- One service account configured via `OPENSTACK_USERNAME`/`OPENSTACK_PASSWORD`
- One OpenStack project (`OPENSTACK_PROJECT_NAME`)
- One cached connection shared across all API consumers in that worker

This is by design — the platform operates within a single OpenStack project. Multi-tenant auth (e.g., user-scoped tokens) is not supported and would require a fundamentally different factory design.

## Recommendations

1. **Add periodic connection health check**: Before returning the cached connection, verify it can reach Keystone. If not, call `invalidate()` and re-create. This would prevent silently stale connections.

2. **Add connection age tracking**: `invalidate()` after a configurable TTL (e.g., 1 hour) to force periodic re-authentication. This reduces the window of silent auth failures.

3. **Add `threading.Lock` to `create()`**: Eliminates the cold-start race condition. Low priority — the race is harmless.

4. **Wire `invalidate()` into error handling**: If an API call returns a 401 (Unauthorized), automatically invalidate the connection and retry once. This provides self-healing for token expiration edge cases.

## Related Files

- `app/clients/openstack/connection.py` — Connection factory
- `app/services/openstack/vm_provisioning_engine.py` — Primary consumer of factory
- `app/core/config/settings.py` — OpenStack configuration fields
