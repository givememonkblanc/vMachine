# OpenStack VM Lifecycle — Engine Architecture

> Phase 6 — VM Lifecycle & Readiness Engine  
> **Validation Status: Dry-Run Validated** (see `docs/vm_engine_validation.md`)

## Positioning

This document describes the **VM Lifecycle Engine** — an async-safe service layer
that controls OpenStack VM lifecycle operations through Nova APIs.

**This is NOT VMware migration.** The engine validates OpenStack VM lifecycle
operations directly. VMware-to-OpenStack migration assessment is covered by
the Phase 4 VMware engine (`docs/vmware_migration_architecture.md`).

---

## 1. Architecture

```
┌─ VMProvisioningEngine ────────────────────────────────────────────┐
│                                                                     │
│  create_vm() ────→ Nova create_server ───→ wait_for_active()       │
│  start_vm()  ────→ Nova start_server  ───→ state validation        │
│  stop_vm()   ────→ Nova stop_server   ───→ state validation        │
│  reboot_vm() ────→ Nova reboot_server ───→ state validation        │
│  delete_vm() ────→ Nova delete_server ───→ wait_for_deleted()      │
│  get_vm()    ────→ Nova get_server                                │
│  list_vms()  ────→ Nova servers                                   │
│                                                                     │
│  Dependencies:                                                      │
│    └── OpenStackConnectionFactory (connection.py)                   │
│          └── openstacksdk Connection                                │
│                └── compute service (Nova)                           │
│                                                                     │
│  Metrics:                                                           │
│    ├── vmware_vm_create_duration_seconds     (Histogram)            │
│    ├── vmware_vm_create_failures_total       (Counter)              │
│    ├── vmware_vm_lifecycle_operations_total  (Counter)              │
│    └── vmware_vm_active_count               (Gauge)                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Supported Operations

| Operation | SDK Method | State Validation | Timeout | Async-Safe |
|-----------|-----------|:----------------:|:-------:|:----------:|
| `create_vm` | `create_server` | Waits for ACTIVE/ERROR | 300s | ✅ |
| `start_vm` | `start_server` | Requires SHUTOFF/STOPPED/SUSPENDED/ERROR | 120s | ✅ |
| `stop_vm` | `stop_server` | Requires ACTIVE/PAUSED | 120s | ✅ |
| `reboot_vm` | `reboot_server` | Requires ACTIVE | 120s | ✅ |
| `delete_vm` | `delete_server` | Requires ACTIVE/SHUTOFF/STOPPED/ERROR/SUSPENDED | 120s | ✅ |

### State Transition Rules

```
          ┌──── start ────┐
   SHUTOFF ───────────────→ ACTIVE
   STOPPED ── start ──────→ ACTIVE
   ACTIVE  ── stop ───────→ SHUTOFF
   ACTIVE  ── reboot ─────→ ACTIVE (soft reboot)
   ACTIVE  ── delete ─────→ (deleted)
   SHUTOFF ── delete ─────→ (deleted)
```

Invalid transitions return `409 Conflict` with an `invalid_state_transition`
error code.

---

## 3. API Endpoints

All endpoints are under `/api/v1/openstack/servers`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/servers` | Create VM and wait for ACTIVE |
| GET | `/servers` | List all VMs |
| GET | `/servers/{id}` | Get VM detail |
| POST | `/servers/{id}/start` | Power on |
| POST | `/servers/{id}/stop` | Power off |
| POST | `/servers/{id}/reboot` | Soft reboot |
| DELETE | `/servers/{id}` | Delete VM |
| GET | `/servers/active/count` | Active VM count |

These are minimal validation endpoints — not a production provisioning portal.
No frontend/UI is provided.

### Create VM Input Schema

```json
{
  "name": "my-vm",
  "flavor_id": "m1.tiny",
  "image_id": "cirros-0.6.2",
  "network_ids": ["net-uuid"],
  "keypair": "my-key",
  "security_groups": ["default"],
  "availability_zone": "nova",
  "metadata": {"env": "test"}
}
```

---

## 4. Timeout & Error Handling

| Concern | Mechanism |
|---------|-----------|
| Blocking SDK calls | `call_with_timeout()` — runs in thread pool; raises `asyncio.TimeoutError` |
| Provisioning stuck | `_wait_for_active()` — polls every 3s, aborts after 300s |
| Deletion stuck | `_wait_for_deleted()` — polls every 3s, aborts after 60s |
| API errors | Wrapped in `OpenStackIntegrationException` (502) |
| Invalid state | `AppException` (409) with `invalid_state_transition` code |
| Server not found | `AppException` (404) with `server_not_found` code |
| Create failure | Automatic cleanup — deleted server is removed |

---

## 5. Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vmware_vm_create_duration_seconds` | Histogram | `status` (success/failed) | VM creation latency |
| `vmware_vm_create_failures_total` | Counter | `error_type` | Creation failure count |
| `vmware_vm_lifecycle_operations_total` | Counter | `operation`, `status` | Lifecycle op count |
| `vmware_vm_active_count` | Gauge | — | Current ACTIVE VM count |

All metrics are exposed through the existing `/metrics` endpoint.

---

## 6. Cleanup Guarantees

The engine and validation script guarantee cleanup:

1. **On create failure**: `_cleanup_failed_server()` deletes the partially-created VM
2. **On validation failure**: The `finally` block in the validation script deletes any
   remaining VM
3. **On script exit** (any path): `ValidationResult.server_cleaned_up` confirms deletion

---

## 7. Current Limitations

| Limitation | Impact | Future |
|------------|--------|--------|
| Single-region only | No multi-region provisioning | OpenStack client supports regions |
| No volume attachment | Create VM without additional volumes | `block_device_mapping` support |
| No floating IP allocation | VMs get only private IPs | Neutron floating IP integration |
| Poll-based wait | 3s interval, not event-driven | Nova event notifications |
| Sequential lifecycle | Full flow is sequential | Batch operations in validation |
| No scheduler hints | No `scheduler_hints` in create | Extend `VMCreateRequest` |

---

*Document generated for Phase 6 — VM Lifecycle & Readiness Engine*
