# Security Hardening Report

> API authentication, audit logging, and secret management for the VM Lifecycle Engine.
> Last updated: 2026-05-11

## 1. API Authentication Boundary

### What Was Implemented

A lightweight API key guard was added to the VM lifecycle router (`/api/v1/openstack/servers`):

- **Dependency**: `app/core/auth.py::verify_api_key()` — reads `X-API-Key` header
- **Configuration**: `API_KEY` env var (maps to `settings.api_key`)
- **Behavior**:
  - Empty key (default) → guard is a no-op, all requests pass through
  - Key configured → `X-API-Key` header must match exactly
  - Missing header → 401 Unauthorized
  - Wrong key → 403 Forbidden
- **Scope**: Applied to all 8 lifecycle routes via `APIRouter(dependencies=[...])`

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Static bearer key, not per-user tokens | Matches the single-service-account architecture. Full IAM is out of scope. |
| No-op when key is empty | Enables development without configuration overhead. Operators must explicitly set `API_KEY` to enable auth. |
| Router-level, not middleware | Easier to test, easier to selectively apply per-route if needed. |

### What Was NOT Implemented

- **Per-user authentication / RBAC**: The platform operates under a single OpenStack service account. User-scoped tokens would require Keystone trust relationships and are out of scope.
- **Rate limiting**: Not implemented on lifecycle endpoints. If needed, add middleware or use Nginx `limit_req`.
- **Audit of auth failures**: Auth failures are not logged to the audit DB. Only successful lifecycle operations generate audit entries.

## 2. Operation Audit Logging

### What Was Implemented

Structured audit entries are now recorded for every lifecycle operation in `VMProvisioningEngine`. The existing async batch audit infrastructure (`app/services/core/audit_service.py`) is used:

| Operation | Action | Resource Type |
|-----------|--------|---------------|
| VM create | `vm.create` | `vm` |
| VM start | `vm.start` | `vm` |
| VM stop | `vm.stop` | `vm` |
| VM reboot | `vm.reboot` | `vm` |
| VM delete | `vm.delete` | `vm` |

Each entry includes:
```json
{
  "action": "vm.create",
  "resource_type": "vm",
  "resource_id": "<nova-server-uuid>",
  "status": "success|failed",
  "payload": {
    "elapsed_seconds": 17.8,
    "error_type": "TimeoutError"  // only on failure
  }
}
```

Entries are persisted to the `audit_logs` database table via an async batch queue (flush: 20 entries or 2 seconds, whichever comes first).

### What Is NOT Logged

- No credentials, tokens, or secrets
- No request payloads (VM names, flavor IDs, image IDs)
- No caller identity (no user context available in current auth model)

### Limitations

| Limitation | Impact | Future Improvement |
|------------|--------|-------------------|
| No caller identity | Cannot attribute operations to specific users | Add when user auth is implemented |
| Sync API logs only | Background worker actions not audited | Extend if workers perform lifecycle ops |
| Batch persistence | Up to 2s delay before entries appear in DB | Acceptable for operational auditing |

## 3. Secret Management

### Current State

| Secret | Storage | Risk |
|--------|---------|------|
| `OPENSTACK_PASSWORD` | `.env` file (in `.gitignore`) | 🟢 Low — not tracked in git |
| `VMWARE_PASSWORD` | `.env` file (in `.gitignore`) | 🟢 Low — not tracked in git |
| `API_KEY` | `.env` file (in `.gitignore`) | 🟢 Low — not tracked in git |

### Residual Risks

1. **Plain-text `.env`**: All secrets are in a single plain-text file on disk. If an attacker gains filesystem access, all credentials are compromised. Mitigation: systemd service runs as `ryzen395` user; file permissions restrict access.

2. **No secret rotation**: No mechanism to rotate credentials without service restart. Manual process: update `.env`, restart Gunicorn workers.

3. **No encryption at rest**: The SQLite database (if used) stores audit logs with operation details but no credentials. PostgreSQL migration is recommended for production.

## 4. Summary

| Security Layer | Status | Notes |
|---------------|--------|-------|
| API auth (lifecycle endpoints) | ✅ Implemented | API key via `X-API-Key` header |
| Audit logging | ✅ Implemented | Async batch queue to DB |
| Secrets in `.gitignore` | ✅ Verified | `.env` not tracked |
| Per-user auth | ❌ Out of scope | Single service account model |
| Rate limiting | ❌ Not implemented | Use Nginx if needed |
| Secret rotation | ❌ Not implemented | Manual restart required |
